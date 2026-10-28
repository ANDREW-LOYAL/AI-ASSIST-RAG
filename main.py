"""Desktop application entry point."""
import sys
from PySide6.QtWidgets import QApplication
from src.gui.main_window import MainWindow


def main():
    """Run the main application loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("IA Assist")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
