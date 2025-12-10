import tempfile
from app.services.openai_service import client


async def transcribe_realtime(file):
    """
    Uses OpenAI's gpt-4o-transcribe model for audio transcription.
    Compatible with webm, wav, mp3, m4a, etc.
    """
    # Choose extension based on MIME type
    ext = ".webm" if file.content_type == "audio/webm" else ".wav"

    # Write temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            # Use the dedicated transcription model
            resp = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file,
            )

        # Return a simple dict the caller expects
        return {
            "text": resp.text,
            "duration": getattr(resp, "duration", None),
            "format": file.content_type,
        }
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
