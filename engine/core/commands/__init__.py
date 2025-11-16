from .handlers.open import OpenHandler
from .handlers.click import ClickHandler
from .handlers.type import TypeHandler
from .handlers.press import PressHandler
from .handlers.wait_for import WaitForHandler
from .handlers.assert_visible import AssertVisibleHandler
from .handlers.assert_text import AssertTextHandler
from .handlers.assert_url import AssertUrlHandler
from .handlers.custom import CustomHandler
from .handlers.double_click import DoubleClickHandler
from .handlers.right_click import RightClickHandler
from .handlers.hover import HoverHandler
from .handlers.focus import FocusHandler
from .handlers.blur import BlurHandler
from .handlers.clear import ClearHandler
from .handlers.select import SelectHandler
from .handlers.upload import UploadHandler
from .handlers.drag import DragHandler
from .handlers.drag_and_drop import DragAndDropHandler
from .handlers.scroll import ScrollHandler
from .handlers.reload import ReloadHandler
from .handlers.back import BackHandler
from .handlers.forward import ForwardHandler
from .handlers.new_tab import NewTabHandler
from .handlers.new_window import NewWindowHandler
from .handlers.switch_tab import SwitchTabHandler
from .handlers.switch_window import SwitchWindowHandler
from .handlers.close_tab import CloseTabHandler
from .handlers.close_window import CloseWindowHandler
from .handlers.download import DownloadHandler

__all__ = [
    "OpenHandler",
    "ClickHandler",
    "TypeHandler",
    "PressHandler",
    "WaitForHandler",
    "AssertVisibleHandler",
    "AssertTextHandler",
    "AssertUrlHandler",
    "CustomHandler",
    "DoubleClickHandler",
    "RightClickHandler",
    "HoverHandler",
    "FocusHandler",
    "BlurHandler",
    "ClearHandler",
    "SelectHandler",
    "UploadHandler",
    "DragHandler",
    "DragAndDropHandler",
    "ScrollHandler",
    "ReloadHandler",
    "BackHandler",
    "ForwardHandler",
    "NewTabHandler",
    "NewWindowHandler",
    "SwitchTabHandler",
    "SwitchWindowHandler",
    "CloseTabHandler",
    "CloseWindowHandler",
    "DownloadHandler",
]
