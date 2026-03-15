"""Gradio UI for the Legal Obligation Extractor."""

import tempfile
import time

import gradio as gr
import pandas as pd

from src.chunker import chunk_document
from src.document_reader import extract_metadata, read_document
from src.excel_writer import create_excel
from src.extractor import extract_obligations_stream


def process_document(file):
    """Generator that yields (progress_html, dataframe, excel_path, obligations_state, meta_state)."""
    if file is None:
        yield "Upload file để bắt đầu.", pd.DataFrame(), None, [], None
        return

    t_start = time.time()
    yield _progress_bar(0, 1, "Đọc văn bản..."), pd.DataFrame(), None, [], None

    try:
        text = read_document(file.name)
    except Exception as e:
        yield f"<b style='color:red'>Lỗi đọc file: {e}</b>", pd.DataFrame(), None, [], None
        return

    meta = extract_metadata(text)
    chunks = chunk_document(text)
    n = len(chunks)
    header = f"<b>{meta.so_van_ban}</b> — {n} điều"

    all_obligations = []
    skipped = []
    df = pd.DataFrame(columns=["Điều", "Loại", "Tiêu đề", "Nghĩa vụ pháp luật", "Hành động TCB", "Chủ thể tương tác", "Chủ thể hoạt động"])
    info = None

    for info in extract_obligations_stream(chunks):
        if info.phase == "skip":
            skipped.append(info.article_label)
        if info.phase == "done" and info.new_obligations:
            all_obligations.extend(info.new_obligations)
            df = _build_df(all_obligations)
        yield _build_status(header, info, skipped, t_start), df, None, list(all_obligations), meta

    # Generate Excel
    elapsed = time.time() - t_start
    if not all_obligations:
        yield header + "<br><b>Không tìm thấy nghĩa vụ nào.</b>", df, None, [], None
        return

    excel_buf = create_excel(
        all_obligations, meta.ten_van_ban, meta.so_van_ban, meta.ngay_hieu_luc,
    )
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=f"__{meta.so_van_ban.replace('/', '.')}.xlsx",
        prefix="NghiaVu_",
    )
    tmp.write(excel_buf.getvalue())
    tmp.close()

    final = _build_status(header, info, skipped, t_start)
    final += (
        f"<div style='margin-top:8px;padding:8px;background:#e8f5e9;border-radius:6px'>"
        f"<b style='color:#2e7d32'>Hoàn tất! {len(all_obligations)} nghĩa vụ "
        f"trong {_fmt(elapsed)}</b></div>"
    )
    yield final, df, tmp.name, list(all_obligations), meta


def _on_stop(current_html, obligations, meta):
    stop_msg = (
        "<div style='margin-top:8px;padding:8px;background:#ffebee;border-radius:6px'>"
        "<b style='color:#c62828'>Đã dừng trích xuất.</b></div>"
    )
    html = (current_html or "") + stop_msg

    if not obligations:
        return html, None

    # Generate partial Excel from whatever was collected so far
    ten = meta.ten_van_ban if meta else ""
    so = meta.so_van_ban if meta else "partial"
    ngay = meta.ngay_hieu_luc if meta else ""
    excel_buf = create_excel(obligations, ten, so, ngay)
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=f"__{so.replace('/', '.')}_partial.xlsx",
        prefix="NghiaVu_",
    )
    tmp.write(excel_buf.getvalue())
    tmp.close()

    return html, tmp.name


def _build_df(obligations):
    return pd.DataFrame([
        {
            "Điều": ob.dieu,
            "Loại": {"bat_buoc": "Bắt buộc", "quyen": "Quyền", "dinh_nghia": "Định nghĩa"}.get(ob.loai, ob.loai),
            "Tiêu đề": ob.tieu_de,
            "Nghĩa vụ pháp luật": ob.noi_dung,
            "Hành động TCB": ob.hanh_dong.replace("\n", "<br>") if ob.hanh_dong else "",
            "Chủ thể tương tác": ob.chu_the_tuong_tac,
            "Chủ thể hoạt động": ob.chu_the_hoat_dong,
        }
        for ob in obligations
    ])


def _fmt(secs: float) -> str:
    if secs < 60:
        return f"{secs:.1f}s"
    m, s = divmod(secs, 60)
    return f"{int(m)}m{s:.0f}s"


def _progress_bar(current: int, total: int, detail: str = "") -> str:
    pct = int(current / total * 100) if total > 0 else 0
    color = "#2e7d32" if pct >= 100 else "#4472C4"
    short = (detail[:55] + "...") if len(detail) > 55 else detail
    return (
        f"<div style='margin:4px 0'>"
        f"<span style='font-size:13px'><b>Tiến trình</b> [{current}/{total}] "
        f"<span style='color:#666'>{short}</span></span>"
        f"<div style='background:#e0e0e0;border-radius:4px;height:7px;margin:2px 0'>"
        f"<div style='background:{color};width:{pct}%;height:100%;border-radius:4px;"
        f"transition:width 0.3s'></div></div></div>"
    )


def _build_status(header, info, skipped, t_start):
    parts = [f"<div style='margin-bottom:6px'>{header}</div>"]

    # Progress bar
    if info.phase == "extracting":
        detail = f"Phân loại: {info.article_label}"
    elif info.phase == "streaming":
        detail = f"Đang sinh hành động: {info.article_label}"
    elif info.phase == "skip":
        detail = f"Bỏ qua: {info.article_label}"
    else:
        detail = info.article_label
    parts.append(_progress_bar(info.articles_done, info.total_articles, detail))

    # Elapsed
    parts.append(
        f"<div style='font-size:12px;color:#888;margin:2px 0'>Thời gian: {_fmt(time.time() - t_start)}</div>"
    )

    # Streaming preview
    if info.phase == "streaming" and info.streaming_text:
        # Show last ~500 chars of streaming text as preview
        preview = info.streaming_text
        if len(preview) > 500:
            preview = "..." + preview[-500:]
        preview_escaped = preview.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        parts.append(
            f"<div style='margin:6px 0;padding:8px 10px;background:#f3f0ff;border-radius:6px;"
            f"border-left:3px solid #7c4dff;font-size:12px;font-family:monospace;"
            f"max-height:150px;overflow-y:auto;white-space:pre-wrap;word-break:break-word'>"
            f"<b style='color:#7c4dff'>Action streaming ({len(info.streaming_text)} chars):</b><br>"
            f"{preview_escaped}</div>"
        )

    # Skipped warnings
    if skipped:
        items = "".join(f"<li>{s}</li>" for s in skipped)
        parts.append(
            f"<div style='margin:6px 0;padding:6px 8px;background:#fff3e0;border-radius:6px;"
            f"border-left:3px solid #ff9800;font-size:12px'>"
            f"<b style='color:#e65100'>Bỏ qua ({len(skipped)} điều quá dài):</b>"
            f"<ul style='margin:2px 0 0 16px;padding:0'>{items}</ul></div>"
        )

    # Timeline
    if info.timeline:
        rows = []
        for e in info.timeline:
            icon = "⏭️" if e.step == "skip" else "📄"
            short_label = e.label if len(e.label) <= 45 else e.label[:42] + "..."
            rows.append(
                f"<tr style='font-size:12px;border-bottom:1px solid #eee'>"
                f"<td style='padding:2px 6px;color:#888;white-space:nowrap'>{_fmt(e.timestamp)}</td>"
                f"<td style='padding:2px 6px;color:#555'>{icon} {short_label}</td>"
                f"<td style='padding:2px 6px;font-weight:600;white-space:nowrap'>{_fmt(e.duration)}</td>"
                f"<td style='padding:2px 6px;color:#666'>{e.detail}</td></tr>"
            )
        parts.append(
            "<div style='margin-top:8px;max-height:200px;overflow-y:auto;"
            "border:1px solid #e0e0e0;border-radius:6px'>"
            "<table style='width:100%;border-collapse:collapse'>"
            "<tr style='background:#f5f5f5;font-size:11px;font-weight:600'>"
            "<td style='padding:3px 6px'>Thời gian</td>"
            "<td style='padding:3px 6px'>Điều</td>"
            "<td style='padding:3px 6px'>Thời lượng</td>"
            "<td style='padding:3px 6px'>Kết quả</td></tr>"
            + "".join(rows)
            + "</table></div>"
        )

    return "".join(parts)


# --- Build Gradio UI ---
with gr.Blocks(title="Trích xuất Nghĩa vụ Tuân thủ") as app:
    gr.Markdown("## Trích xuất Nghĩa vụ Tuân thủ Pháp luật")

    obligations_state = gr.State([])
    meta_state = gr.State(None)

    with gr.Row():
        with gr.Column(scale=2):
            file_input = gr.File(
                label="Upload văn bản pháp luật (.doc / .docx)",
                file_types=[".doc", ".docx"],
            )
            run_btn = gr.Button("Phân tích", variant="primary")
            stop_btn = gr.Button("Dừng & Tải Excel", variant="stop")
            progress_html = gr.HTML(value="Upload file và bấm Phân tích để bắt đầu.")

        with gr.Column(scale=3):
            results_table = gr.Dataframe(
                headers=["Điều", "Loại", "Tiêu đề", "Nghĩa vụ pháp luật", "Hành động TCB", "Chủ thể tương tác", "Chủ thể hoạt động"],
                datatype=["str", "str", "str", "html", "html", "str", "str"],
                label="Kết quả trích xuất",
                interactive=False,
                wrap=True,
                column_widths=["60px", "80px", "150px", "350px", "300px", "150px", "150px"],
                max_height=800,
            )
            excel_file = gr.File(label="Tải Excel", visible=True)

    run_event = run_btn.click(
        fn=process_document,
        inputs=[file_input],
        outputs=[progress_html, results_table, excel_file, obligations_state, meta_state],
    )
    stop_btn.click(
        fn=_on_stop,
        inputs=[progress_html, obligations_state, meta_state],
        outputs=[progress_html, excel_file],
        cancels=[run_event],
    )

if __name__ == "__main__":
    app.launch(theme=gr.themes.Soft())
