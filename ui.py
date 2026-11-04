# ============================================================
# ui.py —— 界面相关：聊天记录、知识库面板、侧边栏
# ============================================================
import streamlit as st

import config
from session import save_session, generate_session_name, load_sessions, load_session, delete_session


def render_chat_history() -> None:
    """显示当前会话的全部聊天记录。"""
    st.caption(f"当前会话：{st.session_state.current_session}")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])


def render_knowledge_panel(knowledge) -> None:
    """在侧边栏渲染知识库上传与清空区域。"""
    st.divider()
    st.subheader("知识库（RAG）")

    uploader_key = f"knowledge_uploader_{st.session_state.knowledge_clear_counter}"
    uploaded_files = st.file_uploader(
        "上传文档作为知识库",
        type=["txt", "md", "pdf", "docx"],
        accept_multiple_files=True,
        key=uploader_key,
    )

    if uploaded_files:
        for uploaded in uploaded_files:
            raw = uploaded.read()
            file_id = f"{uploaded.name}:{len(raw)}"
            if file_id in st.session_state.knowledge_ids:
                continue

            result = knowledge.add_document(uploaded.name, raw, origin="upload")
            if result.status == "added":
                st.success(f"已导入《{uploaded.name}》，切成 {result.chunks} 个片段。")
                st.session_state.knowledge_ids.add(file_id)
            elif result.status == "exists":
                st.session_state.knowledge_ids.add(file_id)
            elif result.status == "empty":
                st.warning(f"《{uploaded.name}》没有可用的文字内容。")
            elif result.status == "failed":
                st.warning(f"《{uploaded.name}》解析失败：{result.message}")
            elif result.status == "error":
                st.error(f"《{uploaded.name}》导入失败：{result.message}")

    knowledge_info = knowledge.info()
    for error in knowledge.last_sync_errors:
        st.warning(f"本地文档入库失败：{error}")

    st.caption(
        f"本地 docs：{knowledge_info['documents']} 个文档 · "
        f"网页上传：{knowledge_info['uploads']} 个文档 · "
        f"{knowledge_info['chunks']} 个片段"
    )

    if st.button("清空上传文档", width="stretch", icon="🗑️"):
        knowledge.clear_uploads()
        st.session_state.knowledge_ids = set()
        st.session_state.knowledge_clear_counter += 1
        st.rerun()


def render_sidebar(knowledge) -> None:
    """渲染左侧控制面板。"""
    with st.sidebar:
        st.subheader("AI控制面板")

        if st.button("新建会话", width="stretch", icon="🖊️"):
            save_session()
            st.session_state.messages = []
            st.session_state.current_session = generate_session_name()
            st.rerun()

        st.text("会话历史")
        session_list = load_sessions()

        if not session_list:
            st.caption("暂时没有历史会话")

        for name in session_list:
            col1, col2 = st.columns([4, 1])

            with col1:
                is_current = name == st.session_state.current_session
                if st.button(
                    name,
                    width="stretch",
                    icon="💬",
                    key=f"load_{name}",
                    type="primary" if is_current else "secondary",
                ):
                    if load_session(name):
                        st.rerun()

            with col2:
                if st.button(
                    "",
                    width="stretch",
                    icon="❌",
                    key=f"delete_{name}",
                ):
                    delete_session(name)
                    st.rerun()

        st.divider()

        st.subheader("助手信息")

        nick_name = st.text_input(
            "昵称",
            value=st.session_state.nick_name,
            placeholder="请输入昵称",
        )
        st.session_state.nick_name = nick_name or config.DEFAULT_NICK_NAME

        nature = st.text_input(
            "性格",
            value=st.session_state.nature,
            placeholder="请输入性格",
        )
        st.session_state.nature = nature or config.DEFAULT_NATURE

        st.divider()

        st.subheader("对话模式")
        st.radio(
            "模型怎么回答",
            options=[config.MODE_KB, config.MODE_AGENT],
            key="chat_mode",
            help=(
                "知识库模式：每问一句都先检索你的文档。\n\n"
                "Agent 模式：模型自己判断要不要查资料、要不要算数、要不要看时间。"
            ),
        )
        if st.session_state.chat_mode == config.MODE_AGENT:
            st.caption("🔧 模型自己决定调用哪些工具，回答下方会显示调用轨迹。")
        else:
            st.caption("📚 每次提问都会先检索知识库原文。")

        render_knowledge_panel(knowledge)
