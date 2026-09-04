from __future__ import annotations

import streamlit as st


def apply_app_styles() -> None:
    """全局视觉基线；尽量只使用稳定的语义选择器，避免依赖内部类名。"""
    st.markdown(
        """
        <style>
        .stApp { background: #f6f7f9; }
        [data-testid="stMainBlockContainer"] {
            max-width: 1240px;
            padding-top: 2.1rem;
            padding-bottom: 4rem;
        }
        [data-testid="stSidebar"] {
            background:
                radial-gradient(circle at 12% 8%, rgba(244, 194, 67, .13), transparent 27%),
                linear-gradient(180deg, #fffdf8 0%, #f7f5ef 100%);
            border-right: 1px solid #ebe7dc;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.7rem; }
        .sidebar-brand {
            display: grid;
            gap: 5px;
            padding: 21px 12px 24px;
            margin: 0 0 8px;
            border-bottom: 1px solid rgba(172, 155, 112, .20);
        }
        .sidebar-brand small {
            color: #a17806;
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.16em;
        }
        .sidebar-brand strong {
            color: #202018;
            font-size: 1.45rem;
            font-weight: 780;
            letter-spacing: -.04em;
        }
        .sidebar-brand span { color: #8b877b; font-size: 0.78rem; }
        [data-testid="stSidebar"] [role="radiogroup"] {
            display: grid;
            gap: 12px;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label {
            min-height: 58px;
            padding: 13px 16px;
            color: #4c4a43 !important;
            background: rgba(255,255,255,.86);
            border: 1px solid rgba(213, 208, 194, .92);
            border-radius: 16px;
            box-shadow: 0 5px 18px rgba(55, 48, 30, .04);
            transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label p {
            color: inherit !important;
            font-weight: 650;
            letter-spacing: .01em;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {
            transform: translateX(3px);
            border-color: #d2b34e;
            box-shadow: 0 8px 22px rgba(92, 74, 21, .08);
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            color: #292517 !important;
            background: linear-gradient(135deg, #fff4c9 0%, #ffe48a 100%);
            border-color: #e6bd35;
            box-shadow: 0 10px 26px rgba(155, 117, 8, .15);
        }
        [data-testid="stSidebar"] [role="radiogroup"] input {
            accent-color: #b98900;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            margin-top: 14px;
            background: rgba(255,255,255,.62);
            border: 1px solid rgba(213, 208, 194, .8);
            border-radius: 14px;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.94);
            border-color: #e8e9ed;
            border-radius: 18px;
            box-shadow: 0 8px 28px rgba(24, 31, 42, 0.045);
        }
        .stButton > button, .stDownloadButton > button {
            border-radius: 11px;
            font-weight: 600;
        }
        [data-testid="stImage"] img {
            object-fit: cover;
            border-radius: 13px;
        }
        [class*="st-key-template-card-"] button {
            background: #ffc928;
            border-color: #ffc928;
            color: #171717;
            min-height: 46px;
            font-weight: 750;
        }
        [class*="st-key-template-card-"] button:hover {
            background: #f2bb13;
            border-color: #f2bb13;
            color: #111;
        }
        .st-key-selected-template-summary {
            border-left: 4px solid #ffc928;
        }
        h1, h2, h3 { letter-spacing: -0.025em; }
        .long-press-image img {
            display: block;
            width: 100%;
            height: auto;
            border-radius: 15px;
            box-shadow: 0 10px 28px rgba(20, 24, 31, .10);
            -webkit-touch-callout: default;
            -webkit-user-select: auto;
            user-select: auto;
            touch-action: auto;
        }
        @media (max-width: 640px) {
            [data-testid="stMainBlockContainer"] {
                padding: 1rem 0.35rem 5rem;
            }
            h1 { font-size: 1.72rem !important; line-height: 1.18 !important; }
            h2 { font-size: 1.34rem !important; }
            h3 { font-size: 1.08rem !important; }
            [data-testid="stVerticalBlockBorderWrapper"] {
                border-radius: 15px;
            }
            .stButton > button, .stDownloadButton > button {
                min-height: 48px;
                width: 100%;
                touch-action: manipulation;
            }
            [data-testid="stFileUploaderDropzone"] {
                min-height: 132px;
                padding: 1rem;
            }
            [data-testid="stSidebar"] {
                min-width: min(88vw, 320px);
            }
            [data-testid="stImage"] img {
                max-height: 72vh;
            }
            [class*="st-key-template-card-"] {
                border-radius: 11px !important;
            }
            [data-testid="stHorizontalBlock"]:has([class*="st-key-template-card-"]),
            [data-testid="stHorizontalBlock"]:has([class*="st-key-open_generation_results_"]) {
                display: grid !important;
                grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
                column-gap: 3px !important;
                row-gap: 5px !important;
                width: 100% !important;
                max-width: 100% !important;
                overflow-x: visible !important;
                scrollbar-width: none !important;
            }
            [data-testid="stHorizontalBlock"]:has([class*="st-key-template-card-"])::-webkit-scrollbar,
            [data-testid="stHorizontalBlock"]:has([class*="st-key-open_generation_results_"])::-webkit-scrollbar {
                display: none !important;
            }
            [data-testid="stHorizontalBlock"]:has([class*="st-key-template-card-"]) > [data-testid="stColumn"],
            [data-testid="stHorizontalBlock"]:has([class*="st-key-open_generation_results_"]) > [data-testid="stColumn"] {
                display: block !important;
                flex: none !important;
                width: 100% !important;
                min-width: 0 !important;
                max-width: none !important;
            }
            [data-testid="stHorizontalBlock"]:has([class*="st-key-template-card-"]) [data-testid="stVerticalBlockBorderWrapper"],
            [data-testid="stHorizontalBlock"]:has([class*="st-key-open_generation_results_"]) [data-testid="stVerticalBlockBorderWrapper"] {
                padding: 3px !important;
                border-radius: 9px !important;
            }
            [class*="st-key-template-card-"] [data-testid="stVerticalBlock"] {
                gap: .16rem;
            }
            [class*="st-key-template-card-"] p {
                font-size: .69rem !important;
                line-height: 1.22 !important;
            }
            [class*="st-key-template-card-"] button {
                min-height: 34px !important;
                padding: .25rem .18rem !important;
                font-size: .66rem !important;
                line-height: 1.05 !important;
            }
            [class*="st-key-template-card-"] [data-testid="stImage"] img {
                width: 100% !important;
                border-radius: 6px;
                aspect-ratio: 3 / 4;
                object-fit: cover;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
