import streamlit as st
from dotenv import load_dotenv

from src.task10_generation import generate_with_citation


load_dotenv()

st.set_page_config(
    page_title="Hỏi đáp pháp luật hộ kinh doanh",
    page_icon="⚖️",
    layout="wide",
)

if "messages" not in st.session_state:
    st.session_state.messages = []


def render_sources(sources: list[dict], retrieval_source: str) -> None:
    if not sources:
        return
    with st.expander(f"Nguồn ({len(sources)} · {retrieval_source})"):
        for number, source in enumerate(sources, 1):
            metadata = source["metadata"]
            title = metadata["title"]
            if metadata.get("url"):
                title = f"[{title}]({metadata['url']})"
            st.markdown(
                f"**[{number}]** {title}  \n"
                f"`{metadata['source']}` · chunk {metadata['chunk_index']} · "
                f"{source['retrieval_method']} score {source['score']:.4f}"
            )
            st.caption(source["content"][:600] + ("…" if len(source["content"]) > 600 else ""))


with st.sidebar:
    st.title("Pháp luật hộ kinh doanh")
    st.caption(
        "Trả lời từ các nghị định/thông tư 2025–2026 về đăng ký, thuế, hóa đơn "
        "của hộ kinh doanh và tin tức liên quan. Mỗi ý có citation [n] trỏ tới nguồn."
    )
    top_k = st.slider("Số chunks", 3, 10, 5)
    if st.button("Xóa hội thoại"):
        st.session_state.messages = []

st.title("Hỏi đáp pháp luật hộ kinh doanh")
st.caption("Ví dụ: Hộ kinh doanh có doanh thu bao nhiêu thì không phải nộp thuế?")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        render_sources(message.get("sources", []), message.get("retrieval_source", ""))

query = st.chat_input("Nhập câu hỏi...")

if query:
    st.session_state.messages.append({"role": "user", "content": query})

    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Đang tìm nguồn và soạn câu trả lời..."):
            result = generate_with_citation(query, top_k=top_k)
        st.markdown(result["answer"])
        render_sources(result["sources"], result["retrieval_source"])

    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
        "retrieval_source": result["retrieval_source"],
    })
