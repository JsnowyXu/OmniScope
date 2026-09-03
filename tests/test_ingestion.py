from omniscope.ingestion import make_chunks


def test_chunking_preserves_section_and_pages():
    sections = [type("S", (), {"path": "方法", "text": "第一句。第二句。第三句。", "page_start": 4, "page_end": 5})()]
    chunks = make_chunks(sections, max_chars=8, overlap=2)
    assert chunks
    assert all(chunk.section_path == "方法" for chunk in chunks)
    assert all(chunk.page_start == 4 and chunk.page_end == 5 for chunk in chunks)
