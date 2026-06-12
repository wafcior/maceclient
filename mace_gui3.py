import sys
import time
import threading
import ctypes
import os

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QSlider, QScrollArea, QSizePolicy, QFrame,
    QDialog, QListWidget, QListWidgetItem 
)
from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QTimer, QPoint, QRect, QLocale
)
from PySide6.QtGui import QColor, QFont, QMouseEvent, QIcon
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController, Listener

# --- Wymagane dla manipulacji oknami Windows ---
try:
    import win32gui
    import win32con
    
    # Stałe WinAPI (klucz do stabilności)
    GWL_STYLE = win32con.GWL_STYLE
    GWL_EXSTYLE = win32con.GWL_EXSTYLE
    HWND_TOP = win32con.HWND_TOP
    
except ImportError:
    win32gui = None
    win32con = None
    print("⚠️ Biblioteka pywin32 nie została znaleziona. Funkcje makro i połączenia nie będą działać.")

QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.AnyCountry))

# --- ZMIENNE GLOBALNE I KONFIGURACJA MAKRA ---
mysz = MouseController()
klawiatura = KeyboardController()

KLUCZ_AKTYWUJACY = 'R'
DELAY_ZWYKLE = 0.05
DELAY_SZYBKIE = 0.01
MAKR_JEST_AKTYWNE = False
IS_INJECTED = False 
MINECRAFT_HWND = None 

# --- KLASA DO OBSŁUGI KAFLA MODUŁU Z FUNKCJĄ TOGGLE ---
class MaceModuleTile(QFrame):
    
    COLOR_ENABLED = "#50B737" 
    COLOR_DISABLED = "#E81123"
    COLOR_BACKGROUND = "#2D2D2D"
    COLOR_HOVER = "#3D3D3D"

    def __init__(self, name, bind_text, click_command, parent_window):
        super().__init__(parent_window)
        self.module_name = name
        self.parent_window = parent_window
        self.click_command = click_command
        
        self.is_enabled = self.parent_window.module_states.get(name, True) 

        self.setObjectName("TileSoft")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setFixedSize(300, 150)
        self.setCursor(Qt.CursorShape.PointingHandCursor) 

        tile_layout = QVBoxLayout(self)
        tile_layout.setContentsMargins(15, 15, 15, 15)
        
        name_label = QLabel(name)
        name_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        name_label.setStyleSheet("background: transparent;")
        tile_layout.addWidget(name_label)
        
        tile_layout.addStretch() 

        bottom_layout = QHBoxLayout()
        
        self.bind_label = QLabel(bind_text, objectName="BindTileLabelSoft")
        self.bind_label.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        self.bind_label.setStyleSheet("background: transparent;")
        bottom_layout.addWidget(self.bind_label)
        bottom_layout.addStretch()

        self.button = QPushButton("KONFIGURUJ", objectName="TileButtonSoft")
        self.button.setFixedSize(120, 30)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        if click_command:
            self.button.clicked.connect(click_command)
        else:
            self.button.setEnabled(False)
            self.button.setText("BRAK FUNKCJI")
        
        bottom_layout.addWidget(self.button)
        tile_layout.addLayout(bottom_layout)
        
        self._update_style()
        
    def _update_style(self):
        border_color = self.COLOR_ENABLED if self.is_enabled else self.COLOR_DISABLED
        
        self.setStyleSheet(f"""
            QFrame#TileSoft {{
                background-color: {self.COLOR_BACKGROUND};
                border: 3px solid {border_color}; 
                border-radius: 5px;
            }}
            QFrame#TileSoft:hover {{
                 background-color: {self.COLOR_HOVER};
            }}
            QFrame#TileSoft QLabel {{ background: transparent; }}
        """)
        
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.button.geometry().contains(event.pos()):
                self.is_enabled = not self.is_enabled
                self._update_style()
                
                self.parent_window.module_states[self.module_name] = self.is_enabled
                
                state_text = "WŁĄCZONO" if self.is_enabled else "WYŁĄCZONO"
                self.parent_window.statusBar().showMessage(f"Moduł '{self.module_name}': {state_text}", 2000)

        super().mousePressEvent(event)


# --- KLASA DO OBSŁUGI PRZESUWANIA OKNA KONFIGURACYJNEGO ---
class MovableWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.drag_start = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.globalPosition().toPoint() - self.parent.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.parent.IS_INJECTED:
            if event.buttons() == Qt.MouseButton.LeftButton and self.drag_start:
                self.parent.move(event.globalPosition().toPoint() - self.drag_start)
                event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_start = None
        event.accept()

# --- OKNO WYBORU APLIKACJI ---
class WindowSelectorDialog(QDialog):
    window_selected = Signal(int) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wybierz Okno do Połączenia")
        self.setFixedSize(500, 400)
        self.setModal(True)
        self.selected_hwnd = 0

        self.setStyleSheet("""
            QDialog {
                background-color: #2D2D2D; 
                border: 1px solid #444444; 
                border-radius: 5px;
                color: #DEDEDE;
            }
            QLabel { color: #DEDEDE; font-size: 14px; margin-bottom: 5px; }
            QListWidget { 
                background-color: #3D3D3D; 
                border: 1px solid #555555;
                color: #DEDEDE;
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #555555; 
                color: white;
            }
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #666666;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel("Wybierz aplikację docelową:"))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._select_and_accept)
        self.list_widget.currentRowChanged.connect(self._update_selected_hwnd)

        main_layout.addWidget(self.list_widget)

        button_layout = QHBoxLayout()
        
        self.select_btn = QPushButton("Wybierz i Połącz")
        self.select_btn.clicked.connect(self._select_and_accept)
        self.select_btn.setEnabled(False) 

        self.cancel_btn = QPushButton("Anuluj")
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.select_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        self._populate_window_list()
    
    def _populate_window_list(self):
        if not win32gui:
            self.list_widget.addItem("BŁĄD: Biblioteka pywin32 nie jest dostępna.")
            return

        def callback(hwnd, extra):
            title = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and title and len(title) > 3 and "python" not in title.lower() and "pycharm" not in title.lower() and title != "Wybierz Okno do Połączenia":
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, hwnd)
                self.list_widget.addItem(item)
            return True

        self.list_widget.clear()
        win32gui.EnumWindows(callback, None)
        
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0) 

    def _update_selected_hwnd(self, row):
        item = self.list_widget.item(row)
        if item:
            self.selected_hwnd = int(item.data(Qt.ItemDataRole.UserRole))
            self.select_btn.setEnabled(True)
        else:
            self.select_btn.setEnabled(False)
            self.selected_hwnd = 0

    def _select_and_accept(self):
        if self.list_widget.currentRow() >= 0 and self.selected_hwnd != 0:
            self.window_selected.emit(self.selected_hwnd)
            self.accept()
        else:
             self._update_selected_hwnd(self.list_widget.currentRow())
             if self.selected_hwnd != 0:
                 self.window_selected.emit(self.selected_hwnd)
                 self.accept()


# --- GŁÓWNA APLIKACJA (Mace Client Hub) ---
class MaceClientWindow(QMainWindow):
    
    INITIAL_WIDTH = 800
    INITIAL_HEIGHT = 500
    
    VIEW_MODULES = "ModulesViewSoft"
    VIEW_SETTINGS = "SettingsViewSoft"

    def __init__(self):
        super().__init__()
        
        # Ustawienie globalnych stanów w instancji okna
        self.IS_INJECTED = False
        self.MINECRAFT_HWND = None
        
        self.setWindowTitle("Mace Client - Soft Dark Mode")
        
        if os.path.exists("setting.png"):
            self.setWindowIcon(QIcon("setting.png")) 
        
        self.setGeometry(100, 100, self.INITIAL_WIDTH, self.INITIAL_HEIGHT)
        self.setMinimumSize(self.INITIAL_WIDTH, self.INITIAL_HEIGHT)
        
        # POPRAWKA BŁĘDU: Inicjalizacja kluczowych zmiennych przed użyciem
        self.current_content_widget = None
        self.current_view = None
        
        self.module_states = {
            "Elytra Mace": True, 
            "Shield Slam": True,
            "Pearl": True,
            "Rebind Features": True,
            "Upcoming Feature": True, 
        }
        
        self.main_container = QWidget(objectName="MainWindowContainer")
        self.setCentralWidget(self.main_container)
        
        temp_vlayout = QVBoxLayout(self.main_container)
        temp_vlayout.setContentsMargins(0, 0, 0, 0)
        temp_vlayout.setSpacing(0)
        
        self.content_hlayout = QHBoxLayout()
        self.content_hlayout.setContentsMargins(0, 0, 0, 0)
        self.content_hlayout.setSpacing(0)
        
        self._setup_injector_button() 
        self._setup_styles() 
        self._setup_sidebar()
        self._setup_content_area()
        
        temp_vlayout.addLayout(self.content_hlayout)
        
        self.statusBar().setStyleSheet("color: #AAAAAA; font-size: 10pt;")
        self.statusBar().showMessage("Mace Client gotowy. Kliknij przycisk 'Połącz' na dole, aby wybrać okno docelowe.", 7000)
        
        # Wątki i stany (pozostałe inicjalizacje)
        self.elytra_config_window = None 
        self.bind_tile_label = None
        
        self.listener_thread = KeyboardListenerThread(parent=self)
        self.listener_thread.key_pressed.connect(self._handle_macro_activation)
        self.listener_thread.set_bind(KLUCZ_AKTYWUJACY)
        self.listener_thread.start()
        
        self._set_view_content(self.VIEW_MODULES) 
        self.show()

    # --- Logika Przełączania Widoków ---
    def _handle_modules_click(self):
        if self.current_view != self.VIEW_MODULES:
            self._set_view_content(self.VIEW_MODULES)

    def _handle_settings_click(self):
        if self.current_view == self.VIEW_SETTINGS:
            self._set_view_content(self.VIEW_MODULES)
        else:
            self._set_view_content(self.VIEW_SETTINGS)

    def _set_view_content(self, target_view):
        if self.current_content_widget:
            self.content_stack_layout.removeWidget(self.current_content_widget)
            self.current_content_widget.deleteLater()
            self.current_content_widget = None

        if target_view == self.VIEW_MODULES:
            new_widget = self._create_module_content()
        elif target_view == self.VIEW_SETTINGS:
            new_widget = self._create_settings_content()
        else:
            return 

        self.current_view = target_view
        self.current_content_widget = new_widget
        self.content_stack_layout.addWidget(self.current_content_widget)
        self.current_content_widget.show()
        
        self._update_sidebar_buttons(self.current_view)

    def _update_sidebar_buttons(self, active_view):
        default_style = "background-color: #3D3D3D; border: 1px solid #555555;"
        active_style = "background-color: #555555; border: 1px solid #777777;" 
        
        self.modules_btn.setStyleSheet(default_style)
        self.settings_btn.setStyleSheet(default_style)
        
        if active_view == self.VIEW_MODULES:
            self.modules_btn.setStyleSheet(active_style)
        elif active_view == self.VIEW_SETTINGS:
            self.settings_btn.setStyleSheet(active_style)

    # --- Pasek Boczny i Zawartość ---
            
    def _setup_sidebar(self):
        self.sidebar_widget = QFrame(objectName="SidebarWidgetSoft")
        self.sidebar_widget.setFixedWidth(60) 
        self.sidebar_widget.setFrameShape(QFrame.Shape.StyledPanel)
        self.sidebar_widget.setFrameShadow(QFrame.Shadow.Raised) 

        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(0, 5, 0, 5)
        sidebar_layout.setSpacing(10)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.modules_btn = QPushButton("MOD", objectName="SidebarButtonSoft")
        self.modules_btn.setFixedSize(40, 40)
        self.modules_btn.clicked.connect(self._handle_modules_click)
        sidebar_layout.addWidget(self.modules_btn, 0, Qt.AlignmentFlag.AlignCenter)

        sidebar_layout.addStretch()

        self.settings_btn = QPushButton("UST", objectName="SidebarButtonSoft")
        self.settings_btn.setFixedSize(40, 40)
        self.settings_btn.clicked.connect(self._handle_settings_click) 
        sidebar_layout.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.content_hlayout.addWidget(self.sidebar_widget)

    def _setup_content_area(self):
        self.content_stack = QFrame(objectName="ContentStackSoft")
        self.content_stack_layout = QVBoxLayout(self.content_stack)
        self.content_stack_layout.setContentsMargins(0, 0, 0, 0)
        self.content_stack_layout.setSpacing(0)
        
        self.content_hlayout.addWidget(self.content_stack)

    def _create_module_content(self):
        modules_view = QWidget(objectName=self.VIEW_MODULES)
        modules_layout = QVBoxLayout(modules_view)
        modules_layout.setContentsMargins(0, 0, 0, 0)

        tile_container = QWidget()
        tile_vlayout = QVBoxLayout(tile_container)
        tile_vlayout.setContentsMargins(30, 20, 30, 20)
        tile_vlayout.setSpacing(20)

        row1 = QHBoxLayout()
        self.elytra_tile = MaceModuleTile("Elytra Mace", f"Bind: {KLUCZ_AKTYWUJACY}", self._open_elytra_config, self)
        self.bind_tile_label = self.elytra_tile.bind_label 
        
        row1.addWidget(self.elytra_tile)
        row1.addWidget(MaceModuleTile("Shield Slam", "Bind: F", None, self)) 
        
        row2 = QHBoxLayout()
        row2.addWidget(MaceModuleTile("Pearl", "Bind: G", None, self))
        row2.addWidget(MaceModuleTile("Rebind Features", "Bind: Y", None, self))
        
        row3 = QHBoxLayout()
        row3.addWidget(MaceModuleTile("Upcoming Feature", "Upcoming", None, self))
        row3.addWidget(MaceModuleTile("Upcoming Feature", "Upcoming", None, self))
        
        tile_vlayout.addLayout(row1)
        tile_vlayout.addLayout(row2)
        tile_vlayout.addLayout(row3)
        tile_vlayout.addStretch() 
        
        scroll_area = QScrollArea(objectName="ScrollAreaSoft")
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(tile_container)
        
        modules_layout.addWidget(scroll_area)
        
        modules_layout.addWidget(self.inject_btn)
        
        return modules_view

    def _create_settings_content(self):
        settings_view = QWidget(objectName=self.VIEW_SETTINGS)
        settings_layout = QVBoxLayout(settings_view)
        settings_layout.setContentsMargins(50, 50, 50, 50)
        
        message_label = QLabel("--- USTAWIENIA ---")
        message_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setStyleSheet("color: #FFFFFF;")
        
        description_label = QLabel("Wersja Soft Dark Mode - Klient działający w tle (Overlayless).")
        description_label.setFont(QFont("Segoe UI", 12))
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("color: #CCCCCC;")
        
        settings_layout.addStretch()
        settings_layout.addWidget(message_label)
        settings_layout.addWidget(description_label)
        settings_layout.addStretch()
        
        return settings_view
    
    # --- Logika Połączenia (Overlayless) ---

    def _setup_injector_button(self):
        self.inject_btn = QPushButton("Wybierz Okno i Połącz [CONNECT]", objectName="InjectButtonSoft")
        self.inject_btn.setFixedHeight(60) 
        self.inject_btn.setStyleSheet("""
            QPushButton#InjectButtonSoft {
                background-color: #3D3D3D; 
                color: #DEDEDE;
                border-radius: 5px;
                height: 60px;
                font-weight: bold;
                font-size: 16px;
                margin: 10px 30px 20px 30px; 
                border: 1px solid #555555; 
            }
            QPushButton#InjectButtonSoft:hover {
                background-color: #4D4D4D;
            }
        """)
        self.inject_btn.clicked.connect(self._handle_injection)

    def _handle_macro_activation(self, signal):
        """Obsługuje aktywację makra, sprawdzając stan modułu i połączenia."""
        global MAKR_JEST_AKTYWNE

        if MAKR_JEST_AKTYWNE or not self.IS_INJECTED:
            return
            
        if not self.module_states.get("Elytra Mace", False):
            self.statusBar().showMessage("Moduł 'Elytra Mace' jest WYŁĄCZONY. Aktywacja ignorowana.", 1500)
            return

        self.statusBar().showMessage("Makro 'Elytra Mace' - Aktywacja...", 1500)
        self.macro_thread = MacroLogicThread(
            KLUCZ_AKTYWUJACY, DELAY_ZWYKLE, DELAY_SZYBKIE, parent=self
        )
        if self.elytra_config_window and self.elytra_config_window.isVisible():
            self.macro_thread.status_updated.connect(self.elytra_config_window.update_status)
        
        self.macro_thread.start()


    def _handle_injection(self):
        
        if not win32gui:
            self.inject_btn.setText("BŁĄD: BRAK pywin32")
            return
            
        if self.IS_INJECTED:
            # Zarządzanie pokazaniem/ukryciem
            if self.isVisible():
                 self.hide() 
                 self.inject_btn.setText("POŁĄCZONO. KLIKNIJ ABY POKAZAĆ GUI")
                 self.statusBar().showMessage(f"GUI ukryte. Makro aktywne (HWND: {self.MINECRAFT_HWND})", 3000)
            else:
                 self.show() 
                 if win32gui and self.MINECRAFT_HWND:
                     # Przeniesienie GUI na wierzch
                     win32gui.SetWindowPos(self.winId().__int__(), HWND_TOP, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                 self.inject_btn.setText("POŁĄCZONO. KLIKNIJ ABY UKRYĆ GUI")
                 self.statusBar().showMessage("GUI widoczne. Możesz zmieniać konfigurację.", 3000)
            return

        self.inject_btn.setText("OCZEKIWANIE NA WYBÓR OKNA...")
        QApplication.processEvents()
        
        dialog = WindowSelectorDialog(self)
        dialog.window_selected.connect(self._finalize_injection)
        dialog.exec()
        
        if not self.IS_INJECTED:
             self.inject_btn.setText("Wybierz Okno i Połącz [CONNECT]")


    def _finalize_injection(self, minecraft_hwnd_int):
        
        self.inject_btn.setText("NAWIĄZYWANIE POŁĄCZENIA...")
        QApplication.processEvents()
        
        try:
            self._connect_to_window(minecraft_hwnd_int) 
            
            # Ukrywamy GUI
            self.hide() 
            
            self.inject_btn.setText("POŁĄCZONO. KLIKNIJ ABY POKAZAĆ GUI")
            self.IS_INJECTED = True
            self.MINECRAFT_HWND = minecraft_hwnd_int
            self.statusBar().showMessage(f"Połączono z oknem (HWND: {self.MINECRAFT_HWND}). GUI ukryte, makro aktywne.", 7000)
            
        except Exception as e:
            self.show() 
            self.inject_btn.setText(f"Błąd Połączenia: {e}")
            self.statusBar().showMessage(f"Błąd Połączenia: {e}", 5000)

    def _connect_to_window(self, minecraft_hwnd):
        """Po prostu przechowuje HWND do użycia przez makro. Nie modyfikuje okna GUI."""
        pass 
        
    def update_bind_label(self, new_bind):
        if self.bind_tile_label:
             self.bind_tile_label.setText(f"Bind: {new_bind}")

    def _open_elytra_config(self):
        if self.elytra_config_window is None or not self.elytra_config_window.isVisible():
            self.elytra_config_window = ElytraMaceConfig(self.listener_thread, self)
            self.elytra_config_window.setWindowFlags(
                 Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            )
            self.elytra_config_window.show()

    def closeEvent(self, event):
        self.listener_thread.stop()
        if self.elytra_config_window:
             self.elytra_config_window.close()
        super().closeEvent(event)

    # --- SOFT DARK MODE QSS ---
    
    def _setup_styles(self):
        if sys.platform.startswith('win'):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MaceClient.SoftDark")
            
        self.setStyleSheet(self._get_main_qss()) 
        self.main_container.setStyleSheet("background-color: #1D1D1D;") 

    def _get_main_qss(self):
        return """
            /* --- Ogólne style dla Soft Dark Mode --- */
            * {
                color: #DEDEDE;
                font-family: 'Segoe UI', sans-serif;
                background-color: transparent;
                border: none;
                border-radius: 5px;
            }

            QWidget#MainWindowContainer {
                background-color: #1D1D1D;
                border: 1px solid #444444;
                border-radius: 5px;
            }

            /* --- PASEK BOCZNY --- */
            QFrame#SidebarWidgetSoft {
                background-color: #2D2D2D; 
                border-right: 1px solid #444444;
                border-radius: 5px;
            }
            
            QPushButton[objectName^="SidebarButtonSoft"] {
                background-color: #3D3D3D;
                border: 1px solid #555555;
            }
            QPushButton[objectName^="SidebarButtonSoft"]:hover {
                background-color: #555555;
            }
            
            /* --- ELEMENTY WEWNĘTRZNE KAFELKÓW --- */
            /* Sam kafelek jest stylizowany przez MaceModuleTile._update_style */

            QLabel#BindTileLabelSoft {
                 color: #AAAAAA; 
                 font-weight: bold;
            }

            /* --- PRZYCISKI W KAELKACH --- */
            QPushButton#TileButtonSoft {
                background-color: #555555; 
                color: #FFFFFF;
                border: none;
                padding: 5px 10px;
            }
            QPushButton#TileButtonSoft:hover {
                background-color: #666666;
            }
            QPushButton#TileButtonSoft:disabled {
                background-color: #3D3D3D;
                color: #888888;
            }

            /* --- SCROLL AREA --- */
            QScrollArea#ScrollAreaSoft {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #2D2D2D; 
                width: 10px; 
            }
            QScrollBar::handle:vertical {
                background: #666666; 
                border-radius: 5px;
                min-height: 20px;
            }
        """

# --- KLASY WĄTKÓW I MAKRA ---

class KeyboardListenerThread(QThread):
    key_pressed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.bind_key = KLUCZ_AKTYWUJACY

    def set_bind(self, key_char):
        self.bind_key = key_char
        QTimer.singleShot(0, lambda: self.parent().update_bind_label(key_char))
        
    def run(self):
        def key_to_str(key):
            try:
                return key.char.upper()
            except AttributeError:
                try:
                    return str(key).split('.')[-1].upper()
                except:
                    return None
        def on_press(key):
            try:
                pressed_key = key_to_str(key)
                if pressed_key and pressed_key == self.bind_key.upper():
                    self.key_pressed.emit("ACTIVATE")
            except Exception:
                pass
        with Listener(on_press=on_press) as listener:
            while self.running:
                listener.join(timeout=0.1) 
                
    def stop(self):
        self.running = False
        self.quit() 
        self.wait() 

class MacroLogicThread(QThread):
    status_updated = Signal(str)

    def __init__(self, bind, delay_z, delay_s, parent=None):
        super().__init__(parent)
        self.bind = bind
        self.delay_z = delay_z
        self.delay_s = delay_s
        self.parent_window = parent

    def run(self):
        global MAKR_JEST_AKTYWNE
        
        target_hwnd = self.parent_window.MINECRAFT_HWND

        if target_hwnd is None:
            self.status_updated.emit("<font color='#FF5555'>Błąd: Brak wybranego okna docelowego.</font>")
            return

        # Aktywacja okna docelowego
        try:
            if win32gui and target_hwnd:
                if not win32gui.IsWindow(target_hwnd) or not win32gui.IsWindowVisible(target_hwnd):
                    self.status_updated.emit("<font color='#FF5555'>Błąd: Okno docelowe jest zamknięte lub ukryte.</font>")
                    return
                
                win32gui.SetForegroundWindow(target_hwnd)
                
            else:
                self.status_updated.emit("<font color='#FF5555'>Błąd: Brak dostępu do win32gui lub HWND.</font>")
                return
        except Exception as e:
            self.status_updated.emit(f"<font color='#FF5555'>Błąd aktywacji okna: {e}</font>")
            return
        
        MAKR_JEST_AKTYWNE = True
        self.status_updated.emit("<font color='#AAAAAA'>Makro Działa...</font>")

        try:
            # --- SEKWENCJA MAKRA ---
            klawiatura.press('5'); klawiatura.release('5'); time.sleep(self.delay_z) 
            mysz.click(Button.right); time.sleep(self.delay_z) 
            mysz.click(Button.x1); time.sleep(self.delay_z) 

            for _ in range(5):
                mysz.click(Button.left); time.sleep(self.delay_s)
            time.sleep(self.delay_z) 
            
            klawiatura.press('5'); klawiatura.release('5'); time.sleep(self.delay_z) 
            mysz.click(Button.right); time.sleep(self.delay_z) 
            klawiatura.press(Key.space); klawiatura.release(Key.space); time.sleep(self.delay_z) 
            klawiatura.press('4'); klawiatura.release('4')
            
            self.status_updated.emit("<font color='#50B737'>Sekwencja Zakończona.</font>")
            
        except Exception as e:
            self.status_updated.emit(f"<font color='#FF5555'>Błąd makra: {e}</font>")
            
        MAKR_JEST_AKTYWNE = False


# --- OKNO KONFIGURACJI MAKRA ---
class ElytraMaceConfig(QWidget):
    
    def __init__(self, listener_thread, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Elytra Mace - Konfiguracja")
        self.setGeometry(200, 200, 480, 420)
        self.listener_thread = listener_thread
        
        self.bind_key_str = KLUCZ_AKTYWUJACY
        self.delay_zwykle_val = DELAY_ZWYKLE
        self.delay_szybkie_val = DELAY_SZYBKIE

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False) 
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_ui()
        
    def _get_config_qss(self):
        return """
            QWidget#ConfigWindowContainer {
                background: #2D2D2D; 
                border: 1px solid #444444; 
                border-radius: 5px;
            }
            QLabel { color: #DEDEDE; font-size: 14px; background: transparent;}
            QLabel#ConfigTitle { 
                color: #FFFFFF; 
                font-size: 16px; 
                font-weight: bold; 
                padding: 2px 10px;
            }
            
            QPushButton#BindButton {
                background-color: #555555;
                color: white;
                border: 1px solid #666666;
                border-radius: 5px;
                padding: 5px 15px;
            }
            QPushButton#BindButton:hover {
                background-color: #666666;
            }
             QSlider::groove:horizontal {
                height: 6px;
                border-radius: 3px;
                background: #3D3D3D;
            }
            QSlider::handle:horizontal {
                background: #AAAAAA;
                width: 12px;
                height: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #888888;
                border-radius: 3px;
            }
            QPushButton#CloseButton { 
                background-color: transparent;
                color: #DEDEDE; 
                border: none; 
            }
            QPushButton#CloseButton:hover { 
                background-color: #E81123; 
                color: #FFFFFF;
            }
        """

    def _setup_ui(self):
        main_container = QWidget(objectName="ConfigWindowContainer")
        self.main_layout.addWidget(main_container)
        self.setStyleSheet(self._get_config_qss())
        
        self.title_bar = MovableWindow(self) 
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background-color: #3D3D3D; border-bottom: 1px solid #444444;")
        
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 5, 0)
        
        title_label = QLabel("Elytra Mace - Konfiguracja", objectName="ConfigTitle")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.close_btn = QPushButton("✖", objectName="CloseButton")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.close)

        title_layout.addWidget(self.close_btn)
        
        config_content = QWidget()
        container_layout = QVBoxLayout(config_content)
        container_layout.setSpacing(15)
        container_layout.setContentsMargins(20, 10, 20, 20)
        config_content.setStyleSheet("background-color: #2D2D2D; border: none;")

        # 1. BIND
        bind_layout = QHBoxLayout()
        bind_layout.addWidget(QLabel("Klawisz Aktywacji (Bind):"))
        
        self.bind_button = QPushButton(self.bind_key_str, objectName="BindButton")
        self.bind_button.setFixedSize(QSize(120, 30))
        self.bind_button.clicked.connect(self._start_bind_capture)
        bind_layout.addWidget(self.bind_button)
        container_layout.addLayout(bind_layout)
        
        # 2. SUWAKI OPÓŹNIENIA
        container_layout.addWidget(QLabel("<hr style='border: 1px solid #444444;'>"))
        
        self.delay_z_label = QLabel(f"Opóźnienie Zwykłe (ms): {int(self.delay_zwykle_val * 1000)}ms")
        container_layout.addWidget(self.delay_z_label)
        self.delay_z_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_z_slider.setRange(10, 500)
        self.delay_z_slider.setValue(int(self.delay_zwykle_val * 1000))
        self.delay_z_slider.valueChanged.connect(self._update_delay_z)
        container_layout.addWidget(self.delay_z_slider)

        self.delay_s_label = QLabel(f"Opóźnienie Szybkie (ms): {int(self.delay_szybkie_val * 1000)}ms")
        container_layout.addWidget(self.delay_s_label)
        self.delay_s_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_s_slider.setRange(5, 100)
        self.delay_s_slider.setValue(int(self.delay_szybkie_val * 1000))
        self.delay_s_slider.valueChanged.connect(self._update_delay_s)
        container_layout.addWidget(self.delay_s_slider)

        # 3. STATUS
        container_layout.addStretch()
        self.status_label = QLabel("<font color='#AAAAAA'>Status: Gotowy</font>")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.status_label)
        
        main_vbox = QVBoxLayout(main_container)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.addWidget(self.title_bar)
        main_vbox.addWidget(config_content)

    def _update_delay_z(self, value):
        self.delay_zwykle_val = value / 1000.0
        self.delay_z_label.setText(f"Opóźnienie Zwykłe (ms): {value}ms")

    def _update_delay_s(self, value):
        self.delay_szybkie_val = value / 1000.0
        self.delay_s_label.setText(f"Opóźnienie Szybkie (ms): {value}ms")

    def _start_bind_capture(self):
        self.bind_button.setText("NACIŚNIJ...")
        self.bind_button.setEnabled(False)
        self.status_label.setText("<font color='#DEDEDE'>Oczekiwanie na nowy klawisz...</font>")
        self.grabKeyboard() 

    def keyPressEvent(self, event):
        key = event.key()
            
        if key in [Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt]:
            return
            
        if event.text(): 
            new_bind = event.text().upper()
        else: 
             new_bind = str(Qt.Key(key)).split('.')[-1].upper().replace("KEY_", "")
        
        self.bind_key_str = new_bind
        self.listener_thread.set_bind(new_bind)
        
        self.bind_button.setText(new_bind)
        self.bind_button.setEnabled(True)
        self.status_label.setText(f"<font color='#50B737'>Bind zmieniony na '{new_bind}'</font>")
        
        self.releaseKeyboard()
        
    def update_status(self, text):
        self.status_label.setText(text)

    def closeEvent(self, event):
        super().closeEvent(event)


# --- ZABEZPIECZONY BLOK URUCHAMIAJĄCY APLIKACJĘ ---
if __name__ == "__main__":
    
    try:
        app = QApplication(sys.argv)
        
        main_window = MaceClientWindow()

        sys.exit(app.exec())
        
    except ImportError as e:
        print("------------------------------------------------------------------")
        print("❗ KRYTYCZNY BŁĄD IMPORTU ❗")
        print(f"Szczegóły błędu: {e}")
        print("\n✅ ROZWIĄZANIE:")
        print("    pip install PySide6 pynput pywin32")
        print("\n------------------------------------------------------------------")
        input("\nNaciśnij ENTER, aby zamknąć konsolę...")
        sys.exit(1)
        
    except Exception as e:
        print("------------------------------------------------------------------")
        print("❌ KRYTYCZNY BŁĄD PODCZAS URUCHAMIANIA GUI! ❌")
        print(f"Szczegóły błędu: {e}")
        print("------------------------------------------------------------------")
        input("\nNaciśnij ENTER, aby zamknąć konsolę...")
        sys.exit(1)