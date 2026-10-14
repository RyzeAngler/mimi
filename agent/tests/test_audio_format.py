from mimi_agent.audio.pcm import PcmFormat, iter_bytes, validate_pcm_chunk


def test_mimi_pcm_contract() -> None:
    audio_format = PcmFormat()
    audio_format.validate()
    assert audio_format.name == "pcm_s16le"
    assert audio_format.frame_bytes == 2
    assert list(iter_bytes(b"abcdef", 2)) == [b"ab", b"cd", b"ef"]


def test_pcm_chunk_must_align_to_sample_frames() -> None:
    try:
        validate_pcm_chunk(b"x", PcmFormat())
    except ValueError:
        pass
    else:
        raise AssertionError("an odd PCM byte count should be rejected")
