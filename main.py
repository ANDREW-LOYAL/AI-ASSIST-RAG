"""Desktop application entry point."""
import sys
from PySide6.QtWidgets import QApplication
<<<<<<< HEAD
from src.gui.main_window import MainWindow
=======
from src.ui.main_window import MainWindow
>>>>>>> 62b0e5e12e28d4fa64463c9d6bf708e53378ac46


def main():
    """Run the main application loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("IA Assist")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
