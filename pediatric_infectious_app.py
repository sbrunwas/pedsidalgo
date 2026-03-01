"""Compatibility shim.

Canonical Streamlit app entrypoint is `app.py`.
"""

from app import generate_assessment, main


if __name__ == "__main__":
    main()
