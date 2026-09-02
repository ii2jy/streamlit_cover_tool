from __future__ import annotations

import socket
from io import BytesIO

import streamlit as st


def get_lan_ip() -> str | None:
    """Return a useful private IPv4 address for another device on the LAN."""
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return None
    private = [
        ip
        for ip in addresses
        if ip.startswith(("192.168.", "10.", "172.")) and not ip.startswith("127.")
    ]
    return private[0] if private else None


def make_qr_png(text: str) -> BytesIO | None:
    try:
        import qrcode
    except ImportError:
        return None
    image = qrcode.make(text)
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


def render_mobile_access(port: int = 8501) -> None:
    ip = get_lan_ip()
    with st.expander("手机访问", icon=":material/phone_iphone:"):
        if not ip:
            st.caption("暂时未识别到局域网地址，请确认电脑已连接 Wi-Fi。")
            return
        url = f"http://{ip}:{port}"
        qr = make_qr_png(url)
        if qr:
            st.image(qr, width=164)
        st.code(url, language=None)
        st.caption("手机与电脑连接同一 Wi-Fi，保持电脑端程序和代理开启，然后扫码访问。")
