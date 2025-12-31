import os
import sys
import time
import socket
import atexit
import ctypes
import logging
import subprocess
from typing import Optional, Any
from dataclasses import dataclass

import mss
import cv2
import psutil
import win32gui
import numpy as np
import pydirectinput
import tomli as tomllib
from pydantic import BaseModel, ValidationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

class SystemConfig(BaseModel):
    start_time: int
    execution: int
    join_story: float
    transaction_waiting: int

class KeyboardConfig(BaseModel):
    hold_time: float
    wait_time: float

class Settings(BaseModel):
    system: SystemConfig
    keyboard: KeyboardConfig

@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int

class AreaType:
    BOTTOM_RIGHT = "bottom_right"
    FULL_SCREEN = "full_screen"

class Scene:
    JOINING_ONLINE = "JOINING_ONLINE"
    STORY_MODE = "STORY_MODE"
    TRANSACTION = "TRANSACTION"

class ConfigLoader:
    @staticmethod
    def load_config(path: str = "config.toml") -> Settings:
        full_path = get_resource_path(path)

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Can't find configuration file: {path}")

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            
            settings = Settings(**data)
            logger.info("Configuration loaded successfully.")
            return settings
            
        except ValidationError as e:
            logger.error(f"Incorrect configuration file format: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error loading Configuration file: {e}")
            sys.exit(1)

class NetworkManager:

    def __init__(self):
        self.rule_name = "GTA5_BLOCK_RULE"
        self.target_processes = ["GTA5.exe", "GTA5_Enhanced.exe"]
        self.cloud_save_domain: str = "cs-gta5-prod.ros.rockstargames.com"
        self.cloud_save_static_ip: str = "192.81.241.171"

    def _get_gta_path(self) -> Optional[str]:
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                if proc.info['name'] in self.target_processes and proc.info['exe']:
                    return proc.info['exe']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def _resolve_cloud_ip(self) -> Optional[str]:
        try:
            ip = socket.gethostbyname(self.cloud_save_domain)
            logger.info(f"Resolved {self.cloud_save_domain} to {ip}")
            return ip
        except socket.error as e:
            logger.error(f"Failed to resolve domain: {e}")
            return None
        
    def _run_netsh(self, command: str) -> None:
        """
        Execute a netsh command silently.
        """
        try:
            subprocess.run(
                command, 
                shell=True, 
                check=False, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.error(f"Netsh command execution failed: {e}")

    def restore_network(self):
        logger.info("Restoring network connection...")
        self._run_netsh(f'netsh advfirewall firewall delete rule name="{self.rule_name}"')
        logger.info("Firewall rules cleaned up. Network restored.")

    def block_network(self) -> bool:
        logger.info("Attempting to block network connection...")

        dynamic_ip: Optional[str] = self._resolve_cloud_ip()

        if dynamic_ip:
            target_ips: str = f"{dynamic_ip},{self.cloud_save_static_ip}"
            logger.info(f"Blocking Cloud Save IPs: {target_ips}")

            cmd: str = (
                f'netsh advfirewall firewall add rule '
                f'name="{self.rule_name}" '
                f'dir=out '
                f'action=block '
                f'protocol=TCP '
                f'remoteip="{target_ips}" '
                f'enable=yes'
            )
            self._run_netsh(cmd)

        else:
            logger.warning("Could not resolve IP. Falling back to blocking GTA V executable.")

            path = self._get_gta_path()

            if not path:
                logger.warning("Can't find GTA V")
                return False
            
            cmd_out: str = (
                f'netsh advfirewall firewall add rule '
                f'name="{self.rule_name}" '
                f'dir=out '
                f'action=block '
                f'program="{path}" '
                f'enable=yes'
            )
            self._run_netsh(cmd_out)

            cmd_in: str = (
                f'netsh advfirewall firewall add rule '
                f'name="{self.rule_name}" '
                f'dir=in '
                f'action=block '
                f'program="{path}" '
                f'enable=yes'
            )
            self._run_netsh(cmd_in)

        logger.info(f"{Colors.RED}Network blocked successfully.{Colors.RESET}")
        return True
    
class SceneDetection:

    def __init__(self):
        self.sct = mss.mss()

        self.window_title = "Grand Theft Auto V"
        self.template_dir = "templates"
        self.threshold = 0.8

        self.targets = {
            "story_mode": {
                "file": "story_mode.png",
                "area": AreaType.FULL_SCREEN,
                "scene": Scene.STORY_MODE
            },
            "joining_online": {
                "file": "joining_online.png",
                "area": AreaType.BOTTOM_RIGHT,
                "scene": Scene.JOINING_ONLINE
            },
            "transaction": {
                "file": "transaction.png",
                "area": AreaType.BOTTOM_RIGHT,
                "scene": Scene.TRANSACTION
            }
        }

        self.templates = {}
        self._load_img()

    def _load_img(self):
        logger.info("Loading template images...")

        count = 0
        for name, config in self.targets.items():
            path = get_resource_path(os.path.join(self.template_dir, config['file']))

            if not os.path.exists(path):
                logger.warning(f"Template not found: {path}")
                continue
            
            img = cv2.imread(path)

            if img is None:
                logger.warning(f"Failed to read image: {path}")
                continue

            self.templates[name] = img
            count += 1
        
        logger.info(f"Successfully loaded {count} templates.")
        
    def _get_win_rect(self, window_title: str) -> Optional[Rect]:
        try:
            hwnd = win32gui.FindWindow(None, window_title)
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                win_rect = Rect(rect[0], rect[1], rect[2] - rect[0], rect[3])
                return win_rect
        
        except Exception as e:
            logger.error(f"Error | get window rect: {e}")
            
        return None
    
    def _get_capture_region(self, win_rect: Rect, area_type: AreaType) -> Rect:
        region = Rect(win_rect.left, win_rect.top, win_rect.width, win_rect.height)

        if area_type == AreaType.BOTTOM_RIGHT:
            region.left = int(win_rect.left + win_rect.width * 0.6)
            region.top = int(win_rect.top + win_rect.height * 0.7)
            region.width = int(win_rect.width * 0.4)
            region.height = int(win_rect.height * 0.3)

        if region.left < 0: region.left = 0
        if region.top < 0: region.top = 0

        return region
    
    def detect_scene(self) -> Optional[Scene]:
        win_rect = self._get_win_rect(self.window_title)
        if not win_rect:
            return None
        
        for name, config in self.targets.items():
            template_img = self.templates[name]

            if template_img is None:
                continue

            capture_region = self._get_capture_region(win_rect, config['area'])

            monitor = {
                "left": capture_region.left,
                "top": capture_region.top,
                "width": capture_region.width,
                "height": capture_region.height
            }

            try:
                scr = self.sct.grab(monitor)
                img = np.array(scr)
                img = img[:, :, :3]

                result = cv2.matchTemplate(img, template_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)

                if max_val >= self.threshold:
                    return config['scene']
                    break

            except Exception as e:
                pass

        return None
        
class KeyboardController:

    def __init__(self, hold_time: float = 0.1, wait_time: float = 0.55):
        self.hold = hold_time
        self.wait = wait_time

        pydirectinput.PAUSE = 0.01

    def press(self, key: Any):
        pydirectinput.keyDown(key)
        time.sleep(self.hold)
        pydirectinput.keyUp(key)
        time.sleep(self.wait)

    def to_online(self):
        logger.info("Executing macro: Switch to Online Session...")
        self.press('esc')
        
        for _ in range(5):
            self.press('right')

        self.press('enter')
        self.press('up')
        self.press('enter')
        self.press('up')
        self.press('enter')
        self.press('enter')
        logger.info("Macro 'Switch to Online' completed.")

    def to_offline(self):
        logger.info("Executing macro: Return to Story Mode...")
        self.press('esc')
        self.press('right')
        self.press('enter')

        for _ in range(3):
            self.press('up')

        self.press('enter')
        self.press('enter')
        logger.info("Macro 'Return to Story Mode' completed.")

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False
    
def get_resource_path(relative_path: str):
    base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base_path, relative_path)
    
def main(config: Settings):
    if not is_admin():
        logger.error("Error: This script requires Administrator privileges.")
        return
    
    # initialization
    logger.info("Initializing components...")
    network_manager = NetworkManager()

    atexit.register(network_manager.restore_network)
    logger.info("Cleanup handler registered (Network will restore on exit).")

    scene_detection = SceneDetection()
    keyboard_controller = KeyboardController(
        config.keyboard.hold_time, 
        config.keyboard.wait_time
    )
    
    print("-" * 60)
    print("注意事項:")
    print("開啟腳本後GTA5必須保持前台模式")
    print("偏好 -> 產生點 請設定比較明亮且不會洗澡的地方")
    print("-" * 60)
    print("操作說明:")
    print("請開啟GTA5並進入故事模式")
    print("準備完成後請按Enter執行腳本")
    print(f"腳本將會等待{config.system.start_time}秒後執行")
    print("-" * 60)

    input(">>> 按 Enter 啟動腳本...")
    
    logger.info(f"Waiting {config.system.start_time} seconds...")
    time.sleep(config.system.start_time)

    print("\n>>> 開始執行腳本")
    
    network_manager.restore_network()

    for i in range(config.system.execution):
        cycle_num = i + 1
        logger.info(f"{Colors.GREEN}=== Starting Cycle {cycle_num}/{config.system.execution} ==={Colors.RESET}")

        transaction_seen = False
        transaction_end_time = 0
        is_network_blocked = False
        is_returning_offline = False

        last_scene = None

        keyboard_controller.to_online()

        while True:
            scene = scene_detection.detect_scene()

            if scene and scene != last_scene:
                logger.info(f"Scene Detected: {Colors.BLUE}{scene}{Colors.RESET}")
                last_scene = scene

            if scene == Scene.JOINING_ONLINE:
                if not is_network_blocked:
                    network_manager.block_network()
                    is_network_blocked = True
                time.sleep(0.5)
                continue

            if scene == Scene.TRANSACTION:
                if not transaction_seen:
                    logger.info("Transaction pending...")
                    transaction_seen = True
                transaction_end_time = 0 
                continue

            if transaction_seen and scene != Scene.TRANSACTION and not is_returning_offline:
                if transaction_end_time == 0:
                    transaction_end_time = time.time()
                    logger.info("Transaction disappeared. Waiting for confirmation...")
                
                elapsed = time.time() - transaction_end_time
                if elapsed > config.system.transaction_waiting:
                    logger.info(f"Confirmed transaction finished ({elapsed:.1f}s). Switching to Offline...")
                    keyboard_controller.to_offline()
                    is_returning_offline = True

                time.sleep(0.1) 
                continue

            if is_returning_offline and scene == Scene.STORY_MODE:
                    logger.info("Returned to Story Mode.")
                    logger.info(f"Cooling down for {config.system.join_story}s...")
                    time.sleep(config.system.join_story)
                    
                    network_manager.restore_network()
                    logger.info("Network restored. Cycle complete.")
                    break

            time.sleep(0.1)

        logger.info(f"Cycle {cycle_num} logic finished.")

    logger.info("All execution cycles completed.")
    network_manager.restore_network()
            
if __name__ == "__main__":
    os.system('color')
    config = ConfigLoader.load_config()
    main(config)
