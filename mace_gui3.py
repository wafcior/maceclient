import sys
import time
import threading
import ctypes
import os

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QSlider, QScrollArea, QFrame,
    QDialog, QListWidget, QListWidgetItem, QCheckBox, QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QTimer, QPoint, QRect, QLocale, 
    QPropertyAnimation, QEasingCurve, Property, QAbstractAnimation
)
from PySide6.QtGui import QColor, QFont, QMouseEvent, QIcon, QPainter, QBrush, QPen

# --- Wymagane dla manipulacji oknami Windows ---
try:
    import win32gui
    import win32con
    
    GWL_STYLE = win32con.GWL_STYLE
    GWL_EXSTYLE = win32con.GWL_EXSTYLE
    HWND_TOP = win32con.HWND_TOP
    
except ImportError:
    win32gui = None
    win32con = None
    print("⚠️ Biblioteka pywin32 nie została znaleziona. Funkcje makro i połączenia nie będą działać.")

QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.AnyCountry))

# --- ZMIENNE GLOBALNE I KONFIGURACJA MAKRA ---
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController, Listener

mysz = MouseController()
klawiatura = KeyboardController()

MAKR_JEST_AKTYWNE = False
IS_INJECTED = False 
MINECRAFT_HWND = None 

# Słowniki przechowujące konfiguracje dla modułów
BINDS = {
    "Elytra Mace": 'R', 
    "Shield Slam": 'F',
    "Pearl": 'G',
    "Rebind Features": 'Y',
    "Upcoming Feature": 'NONE'
}

DELAYS_Z = {
    "Elytra Mace": 0.05,
    "Shield Slam": 0.05,
    "Pearl": 0.05,
    "Rebind Features": 0.05,
    "Upcoming Feature": 0.05
}

DELAYS_S = {
    "Elytra Mace": 0.01,
    "Shield Slam": 0.01,
    "Pearl": 0.01,
    "Rebind Features": 0.01,
    "Upcoming Feature": 0.01
}

MODULE_STATES = {
    "Elytra Mace": True, 
    "Shield Slam": True,
    "Pearl": True,
    "Rebind Features": True,
    "Upcoming Feature": False, 
}

# --- KONTROLKI UI Z ANIMACJAMI ---

class AnimatedToggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 3
        self.animation = QPropertyAnimation(self, b"position")
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setDuration(200)
        self.stateChanged.connect(self.setup_animation)

    @Property(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def setup_animation(self, value):
        self.animation.stop()
        if value:
            self.animation.setEndValue(24)
        else:
            self.animation.setEndValue(3)
        self.animation.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.isChecked():
            bg_color = QColor("#50B737")
        else:
            bg_color = QColor("#555555")
            
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(int(self._position), 3, 20, 20)
        p.end()

class MaceModuleTile(QFrame):
    COLOR_BACKGROUND = "#242424"
    COLOR_HOVER = "#2A2A2A"

    def __init__(self, name, click_command, parent_window):
        super().__init__(parent_window)
        self.module_name = name
        self.parent_window = parent_window
        self.click_command = click_command

        self.setObjectName("TileSoft")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setFixedSize(300, 150)

        tile_layout = QVBoxLayout(self)
        tile_layout.setContentsMargins(20, 20, 20, 20)
        
        top_layout = QHBoxLayout()
        name_label = QLabel(self.module_name)
        name_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #FFFFFF; background: transparent;")
        top_layout.addWidget(name_label)
        
        top_layout.addStretch()
        
        self.toggle = AnimatedToggle()
        self.toggle.setChecked(MODULE_STATES.get(self.module_name, False))
        self.toggle.clicked.connect(self._on_toggle)
        top_layout.addWidget(self.toggle)
        
        tile_layout.addLayout(top_layout)
        tile_layout.addStretch() 

        bottom_layout = QHBoxLayout()
        
        bind_text = BINDS.get(self.module_name, "NONE")
        self.bind_label = QLabel(f"Bind: {bind_text}", objectName="BindTileLabelSoft")
        self.bind_label.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        self.bind_label.setStyleSheet("color: #AAAAAA; background: transparent;")
        bottom_layout.addWidget(self.bind_label)
        
        bottom_layout.addStretch()

        self.button = QPushButton("KONFIGURUJ", objectName="TileButtonSoft")
        self.button.setFixedSize(110, 32)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        if self.click_command:
            self.button.clicked.connect(lambda: self.click_command(self.module_name, self))
        else:
            self.button.setEnabled(False)
            self.button.setText("BRAK FUNKCJI")
            self.button.setStyleSheet("background-color: #333333; color: #666666;")
        
        bottom_layout.addWidget(self.button)
        tile_layout.addLayout(bottom_layout)
        
        self.setStyleSheet(f"""
            QFrame#TileSoft {{
                background-color: {self.COLOR_BACKGROUND};
                border: 1px solid #333333; 
                border-radius: 8px;
            }}
            QFrame#TileSoft:hover {{
                 background-color: {self.COLOR_HOVER};
                 border: 1px solid #444444;
            }}
        """)
        
    def _on_toggle(self):
        is_enabled = self.toggle.isChecked()
        MODULE_STATES[self.module_name] = is_enabled
        state_text = "WŁĄCZONO" if is_enabled else "WYŁĄCZONO"
        self.parent_window.statusBar().showMessage(f"Moduł '{self.module_name}': {state_text}", 2000)

    def update_bind_display(self):
        bind_text = BINDS.get(self.module_name, "NONE")
        self.bind_label.setText(f"Bind: {bind_text}")

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
        if hasattr(self.parent, 'IS_INJECTED') and self.parent.IS_INJECTED:
            return
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_start:
            self.parent.move(event.globalPosition().toPoint() - self.drag_start)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_start = None
        event.accept()


# --- OKNA DIALOGOWE I KONFIGURACYJNE ---

class WindowSelectorDialog(QDialog):
    window_selected = Signal(int) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wybierz Okno do Połączenia")
        self.setFixedSize(500, 420)
        self.setModal(True)
        self.selected_hwnd = 0

        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E; 
                border: 1px solid #333333; 
                border-radius: 8px;
            }
            QLabel { color: #E0E0E0; font-size: 14px; font-weight: bold; margin-bottom: 5px; }
            QListWidget { 
                background-color: #242424; 
                border: 1px solid #333333;
                border-radius: 5px;
                color: #CCCCCC;
                padding: 5px;
                font-size: 13px;
                outline: 0;
            }
            QListWidget::item { padding: 8px; border-radius: 4px; }
            QListWidget::item:hover { background-color: #2A2A2A; }
            QListWidget::item:selected {
                background-color: #3A3A3A; 
                color: #FFFFFF;
                border: 1px solid #555555;
            }
            QPushButton {
                background-color: #333333;
                color: white;
                border: 1px solid #444444;
                border-radius: 5px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #444444; }
            QPushButton:disabled { background-color: #222222; color: #555555; border: 1px solid #2A2A2A; }
            QScrollBar:vertical { border: none; background: #1E1E1E; width: 10px; }
            QScrollBar::handle:vertical { background: #444444; border-radius: 5px; min-height: 20px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        main_layout.addWidget(QLabel("Wybierz aplikację docelową:"))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._select_and_accept)
        self.list_widget.currentRowChanged.connect(self._update_selected_hwnd)
        main_layout.addWidget(self.list_widget)

        button_layout = QHBoxLayout()
        self.select_btn = QPushButton("WYBIERZ I POŁĄCZ")
        self.select_btn.clicked.connect(self._select_and_accept)
        self.select_btn.setEnabled(False) 

        self.cancel_btn = QPushButton("ANULUJ")
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.select_btn)

        main_layout.addLayout(button_layout)
        self._populate_window_list()
    
    def _populate_window_list(self):
        if not win32gui:
            self.list_widget.addItem("BŁĄD: Biblioteka pywin32 nie jest dostępna.")
            return

        def callback(hwnd, extra):
            title = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and title and len(title) > 3 and "python" not in title.lower() and title != "Wybierz Okno do Połączenia":
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

class ModuleConfigWindow(QWidget):
    def __init__(self, module_name, tile_reference, listener_thread, parent=None):
        super().__init__(parent)
        self.module_name = module_name
        self.tile_reference = tile_reference
        self.listener_thread = listener_thread
        
        self.setWindowTitle(f"{self.module_name} - Konfiguracja")
        self.setGeometry(200, 200, 480, 420)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False) 
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_ui()
        
    def _get_config_qss(self):
        return """
            QWidget#ConfigWindowContainer {
                background: #1E1E1E; 
                border: 1px solid #333333; 
                border-radius: 8px;
            }
            QLabel { color: #E0E0E0; font-size: 14px; background: transparent;}
            QLabel#ConfigTitle { 
                color: #FFFFFF; 
                font-size: 16px; 
                font-weight: bold; 
                padding: 2px 10px;
            }
            QPushButton#BindButton {
                background-color: #333333;
                color: white;
                border: 1px solid #444444;
                border-radius: 5px;
                padding: 5px 15px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton#BindButton:hover { background-color: #444444; }
            QSlider::groove:horizontal {
                height: 6px;
                border-radius: 3px;
                background: #2A2A2A;
            }
            QSlider::handle:horizontal {
                background: #50B737;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover { background: #60C747; }
            QSlider::sub-page:horizontal {
                background: #40A727;
                border-radius: 3px;
            }
            QPushButton#CloseButton { 
                background-color: transparent;
                color: #AAAAAA; 
                border: none; 
                font-weight: bold;
                font-size: 14px;
                border-radius: 4px;
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
        self.title_bar.setFixedHeight(35)
        self.title_bar.setStyleSheet("background-color: #242424; border-bottom: 1px solid #333333; border-top-left-radius: 8px; border-top-right-radius: 8px;")
        
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 0, 5, 0)
        
        title_label = QLabel(f"{self.module_name} - Konfiguracja", objectName="ConfigTitle")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.close_btn = QPushButton("✕", objectName="CloseButton")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.close)
        title_layout.addWidget(self.close_btn)
        
        config_content = QWidget()
        container_layout = QVBoxLayout(config_content)
        container_layout.setSpacing(20)
        container_layout.setContentsMargins(25, 20, 25, 25)

        bind_layout = QHBoxLayout()
        bind_label = QLabel("Klawisz Aktywacji (Bind):")
        bind_label.setFont(QFont("Segoe UI", 14))
        bind_layout.addWidget(bind_label)
        
        current_bind = BINDS.get(self.module_name, "NONE")
        self.bind_button = QPushButton(current_bind, objectName="BindButton")
        self.bind_button.setFixedSize(QSize(120, 35))
        self.bind_button.clicked.connect(self._start_bind_capture)
        bind_layout.addWidget(self.bind_button)
        container_layout.addLayout(bind_layout)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #333333;")
        container_layout.addWidget(separator)
        
        val_z = DELAYS_Z.get(self.module_name, 0.05)
        self.delay_z_label = QLabel(f"Opóźnienie Zwykłe (ms): {int(val_z * 1000)}ms")
        container_layout.addWidget(self.delay_z_label)
        self.delay_z_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_z_slider.setRange(10, 500)
        self.delay_z_slider.setValue(int(val_z * 1000))
        self.delay_z_slider.valueChanged.connect(self._update_delay_z)
        container_layout.addWidget(self.delay_z_slider)

        val_s = DELAYS_S.get(self.module_name, 0.01)
        self.delay_s_label = QLabel(f"Opóźnienie Szybkie (ms): {int(val_s * 1000)}ms")
        container_layout.addWidget(self.delay_s_label)
        self.delay_s_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_s_slider.setRange(5, 100)
        self.delay_s_slider.setValue(int(val_s * 1000))
        self.delay_s_slider.valueChanged.connect(self._update_delay_s)
        container_layout.addWidget(self.delay_s_slider)

        container_layout.addStretch()
        self.status_label = QLabel("<font color='#888888'>Status: Gotowy do konfiguracji</font>")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.status_label)
        
        main_vbox = QVBoxLayout(main_container)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)
        main_vbox.addWidget(self.title_bar)
        main_vbox.addWidget(config_content)

    def _update_delay_z(self, value):
        val_sec = value / 1000.0
        DELAYS_Z[self.module_name] = val_sec
        self.delay_z_label.setText(f"Opóźnienie Zwykłe (ms): {value}ms")

    def _update_delay_s(self, value):
        val_sec = value / 1000.0
        DELAYS_S[self.module_name] = val_sec
        self.delay_s_label.setText(f"Opóźnienie Szybkie (ms): {value}ms")

    def _start_bind_capture(self):
        self.bind_button.setText("NACIŚNIJ...")
        self.bind_button.setEnabled(False)
        self.status_label.setText("<font color='#E0E0E0'>Oczekiwanie na nowy klawisz...</font>")
        self.grabKeyboard() 

    def keyPressEvent(self, event):
        key = event.key()
        if key in [Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt]:
            return
            
        if event.text(): 
            new_bind = event.text().upper()
        else: 
             new_bind = str(Qt.Key(key)).split('.')[-1].upper().replace("KEY_", "")
        
        BINDS[self.module_name] = new_bind
        
        self.bind_button.setText(new_bind)
        self.bind_button.setEnabled(True)
        self.status_label.setText(f"<font color='#50B737'>Zapisano bind '{new_bind}' dla modułu {self.module_name}</font>")
        
        if self.tile_reference:
            self.tile_reference.update_bind_display()
            
        self.listener_thread.refresh_binds()
        self.releaseKeyboard()
        
    def update_status(self, text):
        self.status_label.setText(text)

# --- LOGIKA W TLE (MAKRA I NASŁUCH) ---

class KeyboardListenerThread(QThread):
    key_pressed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.active_binds = {}
        self.refresh_binds()

    def refresh_binds(self):
        self.active_binds = {v.upper(): k for k, v in BINDS.items() if v != 'NONE'}
        
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
                if pressed_key and pressed_key in self.active_binds:
                    module_triggered = self.active_binds[pressed_key]
                    self.key_pressed.emit(module_triggered)
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

    def __init__(self, module_name, parent=None):
        super().__init__(parent)
        self.module_name = module_name
        self.parent_window = parent

    def run(self):
        global MAKR_JEST_AKTYWNE
        
        target_hwnd = getattr(self.parent_window, 'MINECRAFT_HWND', None)

        if target_hwnd is None:
            self.status_updated.emit("<font color='#E81123'>Błąd: Brak wybranego okna docelowego.</font>")
            return

        try:
            if win32gui and target_hwnd:
                if not win32gui.IsWindow(target_hwnd) or not win32gui.IsWindowVisible(target_hwnd):
                    self.status_updated.emit("<font color='#E81123'>Błąd: Okno jest zamknięte lub ukryte.</font>")
                    return
                win32gui.SetForegroundWindow(target_hwnd)
            else:
                self.status_updated.emit("<font color='#E81123'>Błąd: Brak dostępu do win32gui lub HWND.</font>")
                return
        except Exception as e:
            self.status_updated.emit(f"<font color='#E81123'>Błąd aktywacji okna: {e}</font>")
            return
        
        MAKR_JEST_AKTYWNE = True
        self.status_updated.emit(f"<font color='#50B737'>Uruchamianie: {self.module_name}...</font>")

        try:
            delay_z = DELAYS_Z.get(self.module_name, 0.05)
            delay_s = DELAYS_S.get(self.module_name, 0.01)

            if self.module_name == "Elytra Mace":
                klawiatura.press('5'); klawiatura.release('5'); time.sleep(delay_z) 
                mysz.click(Button.right); time.sleep(delay_z) 
                mysz.click(Button.x1); time.sleep(delay_z) 

                for _ in range(5):
                    mysz.click(Button.left); time.sleep(delay_s)
                time.sleep(delay_z) 
                
                klawiatura.press('5'); klawiatura.release('5'); time.sleep(delay_z) 
                mysz.click(Button.right); time.sleep(delay_z) 
                klawiatura.press(Key.space); klawiatura.release(Key.space); time.sleep(delay_z) 
                klawiatura.press('4'); klawiatura.release('4')
            else:
                # Moduły zastępcze - infrastruktura przygotowana na rozbudowę zgodnie z prototypem
                time.sleep(0.1)
                
            self.status_updated.emit("<font color='#50B737'>Sekwencja Zakończona.</font>")
            
        except Exception as e:
            self.status_updated.emit(f"<font color='#E81123'>Błąd makra: {e}</font>")
            
        MAKR_JEST_AKTYWNE = False


# --- GŁÓWNA APLIKACJA (Mace Client Hub) ---

class MaceClientWindow(QMainWindow):
    INITIAL_WIDTH = 850
    INITIAL_HEIGHT = 550
    VIEW_MODULES = "ModulesViewSoft"
    VIEW_SETTINGS = "SettingsViewSoft"

    def __init__(self):
        super().__init__()
        
        self.IS_INJECTED = False
        self.MINECRAFT_HWND = None
        
        self.setWindowTitle("Mace Client - Soft Dark Mode")
        if os.path.exists("setting.png"):
            self.setWindowIcon(QIcon("setting.png")) 
        
        self.setGeometry(100, 100, self.INITIAL_WIDTH, self.INITIAL_HEIGHT)
        self.setMinimumSize(self.INITIAL_WIDTH, self.INITIAL_HEIGHT)
        
        self.current_content_widget = None
        self.current_view = None
        self.config_windows = {}
        
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
        
        self.statusBar().setStyleSheet("color: #888888; font-size: 10pt; background: #121212;")
        self.statusBar().showMessage("Mace Client gotowy. Kliknij przycisk 'POŁĄCZ', aby wybrać okno docelowe.", 7000)
        
        self.listener_thread = KeyboardListenerThread(parent=self)
        self.listener_thread.key_pressed.connect(self._handle_macro_activation)
        self.listener_thread.start()
        
        self._set_view_content(self.VIEW_MODULES) 
        self.show()

    def _handle_modules_click(self):
        if self.current_view != self.VIEW_MODULES:
            self._set_view_content(self.VIEW_MODULES)

    def _handle_settings_click(self):
        if self.current_view != self.VIEW_SETTINGS:
            self._set_view_content(self.VIEW_SETTINGS)

    def _set_view_content(self, target_view):
        if self.current_content_widget:
            # Animacja Fade-Out
            self.fade_out = QGraphicsOpacityEffect(self.current_content_widget)
            self.current_content_widget.setGraphicsEffect(self.fade_out)
            self.anim_out = QPropertyAnimation(self.fade_out, b"opacity")
            self.anim_out.setDuration(150)
            self.anim_out.setStartValue(1.0)
            self.anim_out.setEndValue(0.0)
            self.anim_out.finished.connect(lambda: self._finalize_view_switch(target_view))
            self.anim_out.start()
        else:
            self._finalize_view_switch(target_view)

    def _finalize_view_switch(self, target_view):
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
        
        # Animacja Fade-In
        self.fade_in = QGraphicsOpacityEffect(self.current_content_widget)
        self.current_content_widget.setGraphicsEffect(self.fade_in)
        self.anim_in = QPropertyAnimation(self.fade_in, b"opacity")
        self.anim_in.setDuration(150)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.start()
        
        self._update_sidebar_buttons(self.current_view)

    def _update_sidebar_buttons(self, active_view):
        default_style = "background-color: #1E1E1E; border: none; color: #888888;"
        active_style = "background-color: #2A2A2A; border-left: 3px solid #50B737; color: #FFFFFF;" 
        
        self.modules_btn.setStyleSheet(default_style)
        self.settings_btn.setStyleSheet(default_style)
        
        if active_view == self.VIEW_MODULES:
            self.modules_btn.setStyleSheet(active_style)
        elif active_view == self.VIEW_SETTINGS:
            self.settings_btn.setStyleSheet(active_style)

    def _setup_sidebar(self):
        self.sidebar_widget = QFrame(objectName="SidebarWidgetSoft")
        self.sidebar_widget.setFixedWidth(70) 
        self.sidebar_widget.setFrameShape(QFrame.Shape.StyledPanel)

        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        sidebar_layout.setSpacing(15)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.modules_btn = QPushButton("MOD", objectName="SidebarButtonSoft")
        self.modules_btn.setFixedSize(70, 50)
        self.modules_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.modules_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.modules_btn.clicked.connect(self._handle_modules_click)
        sidebar_layout.addWidget(self.modules_btn)

        self.settings_btn = QPushButton("UST", objectName="SidebarButtonSoft")
        self.settings_btn.setFixedSize(70, 50)
        self.settings_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self._handle_settings_click) 
        sidebar_layout.addWidget(self.settings_btn)
        
        sidebar_layout.addStretch()
        self.content_hlayout.addWidget(self.sidebar_widget)

    def _setup_content_area(self):
        self.content_stack = QFrame(objectName="ContentStackSoft")
        self.content_stack_layout = QVBoxLayout(self.content_stack)
        self.content_stack_layout.setContentsMargins(0, 0, 0, 0)
        self.content_stack_layout.setSpacing(0)
        self.content_hlayout.addWidget(self.content_stack)

    def _open_config(self, module_name, tile_reference):
        if module_name in self.config_windows and self.config_windows[module_name].isVisible():
            self.config_windows[module_name].activateWindow()
            return
            
        new_config = ModuleConfigWindow(module_name, tile_reference, self.listener_thread, self)
        self.config_windows[module_name] = new_config
        new_config.show()

    def _create_module_content(self):
        modules_view = QWidget(objectName=self.VIEW_MODULES)
        modules_layout = QVBoxLayout(modules_view)
        modules_layout.setContentsMargins(0, 0, 0, 0)

        tile_container = QWidget()
        tile_vlayout = QVBoxLayout(tile_container)
        tile_vlayout.setContentsMargins(40, 30, 40, 30)
        tile_vlayout.setSpacing(25)

        row1 = QHBoxLayout()
        row1.addWidget(MaceModuleTile("Elytra Mace", self._open_config, self))
        row1.addWidget(MaceModuleTile("Shield Slam", self._open_config, self)) 
        
        row2 = QHBoxLayout()
        row2.addWidget(MaceModuleTile("Pearl", self._open_config, self))
        row2.addWidget(MaceModuleTile("Rebind Features", self._open_config, self))
        
        row3 = QHBoxLayout()
        row3.addWidget(MaceModuleTile("Upcoming Feature", self._open_config, self))
        row3.addStretch()
        
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
        message_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setStyleSheet("color: #FFFFFF;")
        
        description_label = QLabel("Nowoczesna Wersja PySide6.\nArchitektura wspierająca konfigurację modułową i płynne animacje.")
        description_label.setFont(QFont("Segoe UI", 13))
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("color: #AAAAAA;")
        
        settings_layout.addStretch()
        settings_layout.addWidget(message_label)
        settings_layout.addWidget(description_label)
        settings_layout.addStretch()
        settings_layout.addWidget(self.inject_btn)
        
        return settings_view

    def _setup_injector_button(self):
        self.inject_btn = QPushButton("WYBIERZ OKNO I POŁĄCZ [CONNECT]", objectName="InjectButtonSoft")
        self.inject_btn.setFixedHeight(65) 
        self.inject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.inject_btn.setStyleSheet("""
            QPushButton#InjectButtonSoft {
                background-color: #50B737; 
                color: #FFFFFF;
                border-radius: 8px;
                font-weight: bold;
                font-size: 16px;
                margin: 10px 40px 25px 40px; 
                border: none; 
            }
            QPushButton#InjectButtonSoft:hover {
                background-color: #60C747;
            }
        """)
        self.inject_btn.clicked.connect(self._handle_injection)

    def _handle_macro_activation(self, module_triggered):
        global MAKR_JEST_AKTYWNE

        if MAKR_JEST_AKTYWNE or not self.IS_INJECTED:
            return
            
        if not MODULE_STATES.get(module_triggered, False):
            self.statusBar().showMessage(f"Moduł '{module_triggered}' jest WYŁĄCZONY. Aktywacja ignorowana.", 1500)
            return

        self.statusBar().showMessage(f"Aktywacja makra: '{module_triggered}'...", 1500)
        self.macro_thread = MacroLogicThread(module_triggered, parent=self)
        
        if module_triggered in self.config_windows and self.config_windows[module_triggered].isVisible():
            self.macro_thread.status_updated.connect(self.config_windows[module_triggered].update_status)
        
        self.macro_thread.start()

    def _handle_injection(self):
        if not win32gui:
            self.inject_btn.setText("BŁĄD: BRAK pywin32")
            self.inject_btn.setStyleSheet("background-color: #E81123; color: white; margin: 10px 40px 25px 40px; border-radius: 8px; font-weight: bold; font-size: 16px;")
            return
            
        if self.IS_INJECTED:
            if self.isVisible():
                 self.hide() 
                 self.inject_btn.setText("POŁĄCZONO. KLIKNIJ ABY POKAZAĆ GUI")
                 self.inject_btn.setStyleSheet("background-color: #2A2A2A; border: 1px solid #444444; color: #FFFFFF; margin: 10px 40px 25px 40px; border-radius: 8px; font-weight: bold; font-size: 16px;")
                 self.statusBar().showMessage(f"GUI ukryte. Makro aktywne (HWND: {self.MINECRAFT_HWND})", 3000)
            else:
                 self.show() 
                 if win32gui and self.MINECRAFT_HWND:
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
             self.inject_btn.setText("WYBIERZ OKNO I POŁĄCZ [CONNECT]")

    def _finalize_injection(self, minecraft_hwnd_int):
        self.inject_btn.setText("NAWIĄZYWANIE POŁĄCZENIA...")
        QApplication.processEvents()
        
        try:
            self.hide() 
            self.inject_btn.setText("POŁĄCZONO. KLIKNIJ ABY POKAZAĆ GUI")
            self.inject_btn.setStyleSheet("background-color: #2A2A2A; border: 1px solid #444444; color: #FFFFFF; margin: 10px 40px 25px 40px; border-radius: 8px; font-weight: bold; font-size: 16px;")
            self.IS_INJECTED = True
            self.MINECRAFT_HWND = minecraft_hwnd_int
            self.statusBar().showMessage(f"Połączono z oknem (HWND: {self.MINECRAFT_HWND}). GUI ukryte, makro aktywne.", 7000)
        except Exception as e:
            self.show() 
            self.inject_btn.setText(f"Błąd Połączenia: {e}")
            self.statusBar().showMessage(f"Błąd Połączenia: {e}", 5000)

    def closeEvent(self, event):
        self.listener_thread.stop()
        for config_win in self.config_windows.values():
             config_win.close()
        super().closeEvent(event)

    def _setup_styles(self):
        if sys.platform.startswith('win'):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MaceClient.SoftDarkV2")
            
        self.setStyleSheet(self._get_main_qss()) 
        self.main_container.setStyleSheet("background-color: #121212;") 

    def _get_main_qss(self):
        return """
            * {
                color: #E0E0E0;
                font-family: 'Segoe UI', sans-serif;
                background-color: transparent;
                border: none;
            }
            QWidget#MainWindowContainer {
                background-color: #121212;
            }
            QFrame#SidebarWidgetSoft {
                background-color: #1E1E1E; 
                border-right: 1px solid #2A2A2A;
            }
            QScrollArea#ScrollAreaSoft {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #121212; 
                width: 12px; 
            }
            QScrollBar::handle:vertical {
                background: #333333; 
                border-radius: 6px;
                min-height: 20px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #444444;
            }
        """

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
