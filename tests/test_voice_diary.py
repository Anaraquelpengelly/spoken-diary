import pytest
from unittest.mock import MagicMock, mock_open
import sys

# Mock imports BEFORE importing the main app
# This prevents the script from trying to connect to real services on import
sys.modules["gradio"] = MagicMock()
sys.modules["pcloud"] = MagicMock()
sys.modules["deepgram"] = MagicMock()
sys.modules["pcloud_sdk"] = MagicMock() # Just in case

# Import the module under test
# We use 'from' imports inside the test functions or setup to ensure mocks are ready
import voice_diary_app

@pytest.fixture
def mock_pcloud(mocker):
    """Mock the pCloud client instance"""
    # Create a mock for the PyCloud class
    mock_pc_class = mocker.patch("voice_diary_app.PyCloud")
    mock_instance = mock_pc_class.return_value
    
    # Setup default behaviors
    # Default: List folder returns empty content
    mock_instance.listfolder.return_value = {
        "metadata": {"contents": []}
    }
    # Default: Create folder returns a success ID
    mock_instance.createfolder.return_value = {
        "metadata": {"folderid": 12345}
    }
    
    # Inject this mock into the global 'pc' variable in the app
    voice_diary_app.pc = mock_instance
    return mock_instance

@pytest.fixture
def mock_deepgram(mocker):
    """Mock the Deepgram client instance"""
    # Create a mock for the DeepgramClient class
    mock_dg_class = mocker.patch("voice_diary_app.DeepgramClient")
    mock_instance = mock_dg_class.return_value
    
    # Setup chain: deepgram.listen.rest.v("1").transcribe_file(...)
    mock_rest = mock_instance.listen.rest.v.return_value
    
    # Inject into global 'deepgram'
    voice_diary_app.deepgram = mock_instance
    return mock_rest

def test_ensure_diary_folder_exists(mock_pcloud):
    """Test finding an existing folder"""
    # Setup: listfolder returns a folder named 'Diary'
    mock_pcloud.listfolder.return_value = {
        "metadata": {
            "contents": [
                {"name": "Photos", "isfolder": True, "folderid": 111},
                {"name": "Diary", "isfolder": True, "folderid": 999}
            ]
        }
    }
    
    folder_id = voice_diary_app.ensure_diary_folder()
    
    assert folder_id == 999
    mock_pcloud.listfolder.assert_called_with(folderid=0)
    mock_pcloud.createfolder.assert_not_called()

def test_ensure_diary_folder_creates_new(mock_pcloud):
    """Test creating a folder if it doesn't exist"""
    # Setup: listfolder returns no 'Diary' folder
    mock_pcloud.listfolder.return_value = {
        "metadata": {"contents": []}
    }
    # Setup: createfolder returns new ID
    mock_pcloud.createfolder.return_value = {
        "metadata": {"folderid": 555}
    }
    
    folder_id = voice_diary_app.ensure_diary_folder()
    
    assert folder_id == 555
    mock_pcloud.createfolder.assert_called_with(path='/Diary')

def test_transcribe_audio_success(mock_deepgram, mocker):
    """Test successful transcription"""
    # Mock file opening
    mock_file = mocker.patch("builtins.open", mock_open(read_data=b"fake_audio_data"))
    mocker.patch("os.path.getsize", return_value=1024)
    
    # Mock Deepgram response
    mock_response = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {"transcript": "Hello world this is a test"}
                    ]
                }
            ]
        }
    }
    mock_deepgram.transcribe_file.return_value = mock_response
    
    result = voice_diary_app.transcribe_audio("test_audio.wav")
    
    assert result == "Hello world this is a test"
    # Verify we called transcribe_file with correct payload structure
    args, _ = mock_deepgram.transcribe_file.call_args
    assert args[0] == {"buffer": b"fake_audio_data"}

def test_transcribe_audio_no_file():
    """Test handling of None input"""
    result = voice_diary_app.transcribe_audio(None)
    assert result == "No audio file provided"

def test_save_transcript_success(mock_pcloud, mocker):
    """Test saving transcript flow"""
    # Mock ensure_diary_folder to return a valid ID
    mocker.patch("voice_diary_app.ensure_diary_folder", return_value=1001)
    
    # Mock file operations
    mock_file = mocker.patch("builtins.open", mock_open())
    mocker.patch("os.makedirs")
    mocker.patch("os.path.exists", return_value=True) # For cleanup check
    mocker.patch("os.remove")
    
    result = voice_diary_app.save_transcript("My dear diary...")
    
    assert "Saved:" in result
    # Verify upload was called
    mock_pcloud.uploadfile.assert_called_once()
    # Check arguments: files list should contain a path in /tmp
    call_args = mock_pcloud.uploadfile.call_args
    assert "diary.txt" in call_args[1]['files'][0]
    assert call_args[1]['folderid'] == 1001

def test_save_transcript_empty():
    """Test saving empty text"""
    result = voice_diary_app.save_transcript("")
    assert result == "Cannot save empty transcript"

def test_save_transcript_folder_failure(mocker):
    """Test handling folder access failure"""
    mocker.patch("voice_diary_app.ensure_diary_folder", return_value=None)
    
    result = voice_diary_app.save_transcript("Valid text")
    
    assert "Error: Could not access Diary folder" in result
