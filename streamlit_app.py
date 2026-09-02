"""Streamlit Community Cloud entrypoint.

Keeping the real application in app.py preserves local launch compatibility,
while this conventional filename makes cloud deployment one-click.
"""

from app import main


main()
