import asyncio
from piighost.detector.regex import RegexDetector


def test_detector_finds_email():
    det = RegexDetector()
    detections = asyncio.run(det.detect("Email alice@example.com for info"))
    assert len(detections) == 1
    assert detections[0].label == "EMAIL_ADDRESS"
    assert detections[0].text == "alice@example.com"


def test_detector_finds_multiple_emails():
    det = RegexDetector()
    detections = asyncio.run(det.detect("a@b.com and c@d.org"))
    assert len(detections) == 2
    assert {d.text for d in detections} == {"a@b.com", "c@d.org"}


def test_detector_empty_text():
    det = RegexDetector()
    detections = asyncio.run(det.detect(""))
    assert detections == []


def test_detector_no_matches():
    det = RegexDetector()
    detections = asyncio.run(det.detect("just plain text"))
    assert detections == []


def test_detection_has_correct_positions():
    det = RegexDetector()
    text = "Email alice@example.com now"
    detections = asyncio.run(det.detect(text))
    assert detections[0].position.start_pos == 6
    assert detections[0].position.end_pos == 23
