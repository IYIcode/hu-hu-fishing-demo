# ======== 猛兽派对钓鱼辅助主流程代码整理版（使用 mss 加速截图 + 数字变化检测）========

# ====== 1. 基础模块导入 ======
import ctypes
import time
import sys
import random
import traceback
import os
import platform

import cv2
import numpy as np
import pygetwindow as gw

# ====== 新增：资源路径适配（PyInstaller 兼容）======

# ====== 新增：抛竿成功颜色检测 ROI（请用标记工具重新确认！）======
CAST_SUCCESS_ROI_REL = (0.5645, 0.9193, 0.0049, 0.0065)  # ← 这是你之前说的 F 按钮小区域
TARGET_CAST_SUCCESS_BGR = np.array([41.6, 186.9, 249.6], dtype=np.float32)  # ← 你实测的 BGR 均值
CAST_COLOR_TOLERANCE = 50.0  # 颜色距离阈值




def resource_path(relative_path):
    """ 获取资源文件的真实路径（开发模式 or PyInstaller 打包模式） """
    try:
        # PyInstaller 打包后，资源在临时目录 _MEIxxxxx
        base_path = sys._MEIPASS
    except Exception:
        # 开发模式：使用当前脚本所在目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

DEBUG_SAVE_IMAGES = False

# 依赖检测
try:
    import pyautogui
except Exception as e:
    print("请安装: pip install pyautogui ，报错信息:", e)
    raise

try:
    import mss
except Exception as e:
    print("请安装: pip install mss ，报错信息:", e)
    raise

USE_KEYBOARD = True
try:
    import keyboard
except Exception as e:
    USE_KEYBOARD = False
    print("请安装: pip install keyboard ，报错信息:", e)
    raise

try:
    import win32gui
except Exception as e:
    print("请安装: pip install win32gui ，报错信息:", e)
    raise

# 全局品质计数
star_quality_count = {q: 0 for q in ["标准", "非凡", "稀有", "史诗", "传奇"]}


# ====== 新增：数字变化触发器（用于替代感叹号检测） ======

class NumberChangeTrigger:
    def __init__(self, rel_x=0.873, rel_y=0.897, w=19, h=16, threshold=0.95):
        self.rel_x, self.rel_y = rel_x, rel_y
        self.w, self.h = w, h
        self.similarity_threshold = threshold
        self.base_image = None
        self.last_trigger_time = 0
        self.detection_interval = 0.3
        self.debug_counter = 0  # 用于命名当前帧
        self.base_saved = False  # 确保只保存一次基准图

    def set_base(self, frame, window_w, window_h):
        x = int(self.rel_x * window_w)
        y = int(self.rel_y * window_h)
        region = self._extract(frame, x, y, self.w, self.h)
        if region is not None and region.size > 0:
            raw_base = region.copy()  # 原始彩色图
            self.base_image = self._preprocess(region)
            
            # === 保存基准图（只保存一次）===
            if not self.base_saved and DEBUG_SAVE_IMAGES:
                cv2.imwrite("DEBUG_BASE_RAW.png", raw_base)
                cv2.imwrite("DEBUG_BASE_PROCESSED.png", self.base_image)
                print(f"✅ 基准图已保存！位置: (x={x}, y={y}) 尺寸: {self.w}x{self.h}")
                self.base_saved = True
            return True
        return False

    def should_reel(self, frame, window_w, window_h):
        now = time.time()
        if now - self.last_trigger_time < self.detection_interval:
            return False, 1.0

        if self.base_image is None:
            return False, 1.0

        x = int(self.rel_x * window_w)
        y = int(self.rel_y * window_h)
        region = self._extract(frame, x, y, self.w, self.h)
        if region is None or region.size == 0:
            return False, 1.0

        current_raw = region.copy()
        current = self._preprocess(region)
        if current.shape != self.base_image.shape:
            return False, 1.0

        diff = cv2.absdiff(self.base_image, current)
        diff_ratio = np.sum(diff > 0) / diff.size
        similarity = 1.0 - diff_ratio

        # === 每次比对都保存当前图（带序号）===
        self.debug_counter += 1
        if DEBUG_SAVE_IMAGES:
            cv2.imwrite(f"DEBUG_CURRENT_{self.debug_counter:04d}.png", current_raw)
            cv2.imwrite(f"DEBUG_CURRENT_BIN_{self.debug_counter:04d}.png", current)
        # 可选：也保存差异图
        # cv2.imwrite(f"DEBUG_DIFF_{self.debug_counter:04d}.png", diff)

        # print(f"[{self.debug_counter}] 相似度: {similarity:.4f} | 变化率: {diff_ratio:.2%}")

        if similarity < self.similarity_threshold:
            self.base_image = current.copy()
            self.last_trigger_time = now
            # print(f"🎯 触发收杆！相似度 {similarity:.4f} < 阈值 {self.similarity_threshold}")
            
            return True, similarity

        return False, similarity

    def _extract(self, frame, x, y, w, h):
        h_img, w_img = frame.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _preprocess(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        return binary


# ====== 2. 游戏窗口初始化相关 ======
def find_game_window(title_list=("猛兽派对", "Party Animals", "party animals")):
    for t in title_list:
        try:
            wins = gw.getWindowsWithTitle(t)
            if wins and hasattr(wins[0], '_hWnd'):
                return wins[0]
        except Exception as e:
            print(f"查找窗口 '{t}' 出错: {e}")
    return None

window_titles = ["猛兽派对", "Party Animals", "party animals"]
window = find_game_window(window_titles)
if window is None:
    print(f"无法找到游戏窗口，请确认已经启动，窗口名应为其中之一: {window_titles}")
    sys.exit()
hwnd = window._hWnd

# 自动切换到目标窗口
try:
    window.activate()
    print("已尝试切换至猛兽派对窗口")
    time.sleep(0.8)
except Exception as e:
    print(f"切换窗口失败，需手动切换：{e}")

# ===【关键修改】用 GetWindowRect + GetClientRect 精准对齐客户区===
try:
    # 获取完整窗口（含边框）
    win_left, win_top, win_right, win_bottom = win32gui.GetWindowRect(hwnd)
    client_width, client_height = win32gui.GetClientRect(hwnd)[2:]

    # 计算真实客户区在屏幕上的左上角（去掉标题栏和边框）
    window_left = win_left + (win_right - win_left - client_width) // 2
    window_top = win_top + (win_bottom - win_top - client_height) - (win_right - win_left - client_width) // 2

    window_width = client_width
    window_height = client_height

    if window_width <= 0 or window_height <= 0:
        raise ValueError("窗口宽高读取结果异常！")
    print(f"✅ 客户区定位成功: {window_width}x{window_height} @ ({window_left}, {window_top})")
except Exception as e:
    print("读取窗口大小和位置失败:", e)
    traceback.print_exc()
    sys.exit()



# ====== 新增：F 按钮变化检测器（用于鱼桶满检测）======
F_BUTTON_ROI_REL = (0.4600, 0.9154, 0.0781, 0.0273)  # (x, y, w, h)

class FButtonChangeTrigger:
    def __init__(self, threshold=0.85, min_consecutive=2, interval=0.2):
        self.rel_x, self.rel_y, self.rel_w, self.rel_h = F_BUTTON_ROI_REL
        self.similarity_threshold = threshold
        self.min_consecutive_frames = min_consecutive
        self.detection_interval = interval
        self.base_image = None
        self.last_trigger_time = 0
        self.consecutive_match_count = 0
        self.debug_counter = 0
        self.base_saved = False

    def set_base(self, frame, window_w, window_h):
        """抛竿前设置F按钮区域的基准图"""
        x = int(self.rel_x * window_w)
        y = int(self.rel_y * window_h)
        w = int(self.rel_w * window_w)
        h = int(self.rel_h * window_h)
        
        region = self._extract(frame, x, y, w, h)
        if region is not None and region.size > 0:
            raw_base = region.copy()
            self.base_image = self._preprocess(region)
            
            if not self.base_saved and DEBUG_SAVE_IMAGES:
                cv2.imwrite("DEBUG_FBUTTON_BASE_RAW.png", raw_base)
                cv2.imwrite("DEBUG_FBUTTON_BASE_PROCESSED.png", self.base_image)
                print(f"✅ F按钮基准图已保存！位置: (x={x}, y={y}) 尺寸: {w}x{h}")
                self.base_saved = True
            return True
        return False

    def check_bucket_full(self, frame, window_w, window_h):
        """检查鱼桶是否满了（返回True表示鱼桶满）"""
        now = time.time()
        if now - self.last_trigger_time < self.detection_interval:
            return False, 1.0

        if self.base_image is None:
            return False, 1.0

        x = int(self.rel_x * window_w)
        y = int(self.rel_y * window_h)
        w = int(self.rel_w * window_w)
        h = int(self.rel_h * window_h)
        
        region = self._extract(frame, x, y, w, h)
        if region is None or region.size == 0:
            return False, 1.0

        current_raw = region.copy()
        current = self._preprocess(region)
        if current.shape != self.base_image.shape:
            return False, 1.0

        # 计算相似度
        diff = cv2.absdiff(self.base_image, current)
        diff_ratio = np.sum(diff > 0) / diff.size
        similarity = 1.0 - diff_ratio

        self.debug_counter += 1
        if DEBUG_SAVE_IMAGES:
            cv2.imwrite(f"DEBUG_FBUTTON_CURRENT_{self.debug_counter:04d}.png", current_raw)
            cv2.imwrite(f"DEBUG_FBUTTON_BIN_{self.debug_counter:04d}.png", current)

        # 如果相似度高（没变化），说明鱼桶满了
        if similarity > self.similarity_threshold:
            self.consecutive_match_count += 1
        else:
            self.consecutive_match_count = 0

        # 连续N帧都相似度高，才判定为鱼桶满
        if self.consecutive_match_count >= self.min_consecutive_frames:
            self.last_trigger_time = now
            print(f"✅ 检测到鱼桶满！F按钮区域 {self.min_consecutive_frames} 帧未变化 (相似度: {similarity:.4f})")
            return True, similarity

        return False, similarity

    def _extract(self, frame, x, y, w, h):
        h_img, w_img = frame.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _preprocess(self, img):
        """预处理图像：灰度化 + 二值化"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

        
def play_bucket_full_wav():
    if platform.system() == "Windows":
        try:
            import winsound
            wav_path = resource_path("bucket_full.wav")
            if not os.path.exists(wav_path):
                print("警告：未找到音频文件 bucket_full.wav")
                return
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            print("播放 bucket_full.wav 失败:", e)

def play_sound(file_name):
    if platform.system() != "Windows":
        print("非 Windows 系统，跳过音频播放")
        return
    try:
        import winsound
        file_path = resource_path(file_name)
        if not os.path.exists(file_path):
            print(f"音频文件不存在: {file_path}")
            return
        winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        print(f"播放音频 {file_name} 失败: {e}")



# ====== 4. 鼠标控制（低级）操作相关 ======
PUL = ctypes.POINTER(ctypes.c_ulong)
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)
    ]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)
    ]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),("wParamL", ctypes.c_short),("wParamH", ctypes.c_ushort)]
class INPUT_I(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT),("ki", KEYBDINPUT),("hi", HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", INPUT_I)]
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

SendInput = ctypes.windll.user32.SendInput

def _send_mouse_event(flags, dx=0, dy=0, data=0):
    extra = ctypes.c_ulong(0)
    mi = MOUSEINPUT(dx, dy, data, flags, 0, ctypes.pointer(extra))
    ii = INPUT_I()
    ii.mi = mi
    command = INPUT(INPUT_MOUSE, ii)
    SendInput(1, ctypes.byref(command), ctypes.sizeof(command))

def left_down(): _send_mouse_event(MOUSEEVENTF_LEFTDOWN)
def left_up(): _send_mouse_event(MOUSEEVENTF_LEFTUP)
def left_click():
    left_down()
    time.sleep(0.05)
    left_up()
def move_mouse_abs(x, y):
    sx = ctypes.windll.user32.GetSystemMetrics(0)
    sy = ctypes.windll.user32.GetSystemMetrics(1)
    if sx == 0 or sy == 0:
        print("系统分辨率异常，无法移动鼠标")
        return
    nx = int(x * 65535 / (sx - 1))
    ny = int(y * 65535 / (sy - 1))
    _send_mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny)


# ====== 5. 坐标、颜色与辅助检测 ======
# （以下坐标仅用于 reel() 中的颜色判断，保留不变）
CHECK_X, CHECK_Y = (
    (0.5 * window_width) + window_left + 100 + 50 * (window_width // 1800),
    (0.9478 * window_height) + window_top
)
CHECK_X2, CHECK_Y2 = (
    (0.5444 * window_width) + window_left,
    (0.9067 * window_height) + window_top
)
CHECK_X3, CHECK_Y3 = (
    (0.5083 * window_width) + window_left,
    (0.2811 * window_height) + window_top
)
CHECK_X, CHECK_Y = int(CHECK_X), int(CHECK_Y)
CHECK_X2, CHECK_Y2 = int(CHECK_X2), int(CHECK_Y2)
CHECK_X3, CHECK_Y3 = int(CHECK_X3), int(CHECK_Y3)

def get_pointer_color(x, y):
    try:
        color = pyautogui.pixel(x, y)
        return color
    except Exception as e:
        print(f"获取屏幕坐标({x},{y})像素颜色失败: {e}")
        raise

def color_changed(base_color, new_color, tolerance=12):
    br, bg, bb = base_color
    nr, ng, nb = new_color
    return (abs(br - nr) > tolerance) or (abs(bg - ng) > tolerance) or (abs(bb - nb) > tolerance)

def color_in_range(base_color, new_color, tolerance=12):
    br, bg, bb = base_color
    nr, ng, nb = new_color
    return (abs(br - nr) <= tolerance) and (abs(bg - ng) <= tolerance) and (abs(bb - nb) <= tolerance)


# ====== 6.x 收鱼后五角星品质检测 ======

STAR_REGION_RATIO = (0.40, 0.05, 0.20, 0.15)
COLOR_REGION_OFFSET_X = -45
COLOR_REGION_WIDTH  = 120

quality_color_map = {
    "标准": (183, 186, 193),
    "非凡": (144, 198, 90),
    "稀有": (112, 174, 241),
    "史诗": (171, 102, 251),
    "传奇": (248, 197, 68)
}

def get_dominant_color(region):
    mean_color_bgr = region.mean(axis=(0,1))
    mean_rgb = tuple(int(c) for c in mean_color_bgr[::-1])
    reshaped = region.reshape(-1, 3)
    colors, counts = np.unique(reshaped, axis=0, return_counts=True)
    dominant_bgr = colors[np.argmax(counts)]
    dominant_rgb = tuple(int(c) for c in dominant_bgr[::-1])
    return mean_rgb, dominant_rgb

def color_distance(c1, c2):
    return np.linalg.norm(np.array(c1) - np.array(c2))

def match_quality(rgb_color):
    best_name, best_dist = None, 1e9
    for q_name, qc in quality_color_map.items():
        d = color_distance(rgb_color, qc)
        if d < best_dist:
            best_name, best_dist = q_name, d
    return best_name, best_dist

def detect_star_quality(screenshot=None):
    global star_quality_count
    try:
        # === 获取当前画面 ===
        if screenshot is None:
            with mss.mss() as sct:
                region = {"top": window_top, "left": window_left, "width": window_width, "height": window_height}
                screenshot = sct.grab(region)
            img = np.array(screenshot)[:, :, :3]
        else:
            img = screenshot

        h_img, w_img = img.shape[:2]  # ← 必须添加！

        # === 动态获取模板路径 ===
        template_path = resource_path("star_template.png")
        if not os.path.exists(template_path):
            print(f"❌ 五角星模板缺失: {template_path}")
            return None

        template = cv2.imread(template_path)
        if template is None:
            print("五角星模板加载失败")
            return None

        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        th, tw = template_gray.shape[:2]

        rx, ry, rw, rh = STAR_REGION_RATIO
        sx, sy, sw, sh = int(w_img*rx), int(h_img*ry), int(w_img*rw), int(h_img*rh)
        detect_region = img[sy:sy+sh, sx:sx+sw]
        detect_gray = cv2.cvtColor(detect_region, cv2.COLOR_BGR2GRAY)

        SCALES = [1.0, 0.9, 0.8, 0.7, 0.6]
        best_score = 0
        best_loc = None
        best_tw, best_th = tw, th
        for s in SCALES:
            t_resized = cv2.resize(template_gray, (int(tw*s), int(th*s)), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(detect_gray, t_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_loc = max_loc
                best_tw, best_th = t_resized.shape[1], t_resized.shape[0]

        if best_loc is None or best_score < 0.3:
            print("未检测到五角星（匹配度不足）")
            return None

        top_left = (sx + best_loc[0], sy + best_loc[1])
        bottom_right = (top_left[0] + best_tw, top_left[1] + best_th)

        y1, y2 = top_left[1], bottom_right[1]
        x1 = top_left[0] + tw + COLOR_REGION_OFFSET_X
        x2 = x1 + COLOR_REGION_WIDTH
        color_region = img[y1:y2, x1:x2]

        mean_rgb, dominant_rgb = get_dominant_color(color_region)
        mean_q, mean_dist = match_quality(mean_rgb)
        dom_q, dom_dist = match_quality(dominant_rgb)

        quality = dom_q
        star_quality_count[quality] += 1
        total = sum(star_quality_count.values())
        if 'log_window' in globals() and log_window:
            log_window._update_stats_display() 
        return {"mean": (mean_rgb, mean_q, mean_dist), "dominant": (dominant_rgb, quality, dom_dist)}
 
    except Exception as e:
        print(f"五角星检测异常: {e}")
        traceback.print_exc()
        return None


        
# ====== 7. 主要钓鱼流程 ======
def enhanced_bite_check(fishing_start_time, fbutton_trigger, base_frame):
    """
    增强版咬钩检测，包含 7 秒抛竿失败检查
    """
    timeout = 60
    cast_failure_checked = False
    cast_failure_threshold = 7.0  # 7秒后检查

    trigger = NumberChangeTrigger(
        rel_x=0.873,
        rel_y=0.897,
        w=19,
        h=16,
        threshold=0.95
    )

    time.sleep(0.8)
    with mss.mss() as sct:
        region = {"top": window_top, "left": window_left, "width": window_width, "height": window_height}
        screenshot = sct.grab(region)
        frame = np.array(screenshot)[:, :, :3]
        trigger.set_base(frame, window_width, window_height)

    last_sec = -1
    while True:
        elapsed = time.time() - fishing_start_time

        # ===== 新增：7秒时检查抛竿是否失败 =====
        if not cast_failure_checked and elapsed >= cast_failure_threshold:
            cast_failure_checked = True
            
            with mss.mss() as sct:
                frame = np.array(sct.grab({
                    "top": window_top, "left": window_left,
                    "width": window_width, "height": window_height
                }))[:, :, :3]

            # ===== 7秒抛竿状态颜色检测（使用专用 ROI 和目标颜色）=====
            # print("\n🔍 7秒抛竿状态颜色检测中...")
            cast_success_roi = CAST_SUCCESS_ROI_REL
            target_bgr = TARGET_CAST_SUCCESS_BGR
            tolerance = CAST_COLOR_TOLERANCE

            # 提取 ROI
            rel_x, rel_y, rel_w, rel_h = cast_success_roi
            x = int(rel_x * window_width)
            y = int(rel_y * window_height)
            w = max(1, int(rel_w * window_width))
            h = max(1, int(rel_h * window_height))

            # 边界保护
            if x + w > frame.shape[1] or y + h > frame.shape[0] or w <= 0 or h <= 0:
                print("⚠️ 抛竿检测 ROI 越界，跳过")
            else:
                roi = frame[y:y+h, x:x+w]
                if roi.size > 0:
                    mean_bgr = np.array(cv2.mean(roi)[:3], dtype=np.float32)
                    dist = np.linalg.norm(mean_bgr - target_bgr)
                    # print(f"📏 抛竿颜色距离: {dist:.2f} (阈值: {tolerance})")

                    if dist > tolerance:
                        # print("❌ 7秒检测：F按钮区域颜色异常！判定抛竿失败，重启流程。")
                        return False  # 抛竿失败
                   

        # ===== 原有咬钩检测 =====
        time.sleep(0.05)
        with mss.mss() as sct:
            frame = np.array(sct.grab({
                "top": window_top, "left": window_left,
                "width": window_width, "height": window_height
            }))[:, :, :3]

        should_reel, sim = trigger.should_reel(frame, window_width, window_height)
        if should_reel:
            print(f"🫧咬钩啦！🎣 拉杆！给我上来！")
            sys.stdout.flush()
            return True

        # 动态提示
        current_sec = int(elapsed)
        if current_sec != last_sec:
            sys.stdout.write(f"⏳等鱼儿上钩中... {current_sec} 秒")
            sys.stdout.flush()
            last_sec = current_sec

        if elapsed >= timeout:
            print(f"\r超时！{timeout} 秒内未咬钩")
            return False


def reel(fishing_start_time):
    base_color_orange = (255, 195, 83)
    times = 0
    while True:
        try:
            color_exist = get_pointer_color(CHECK_X, CHECK_Y)
        except Exception as e:
            print("读取像素失败:", e)
            time.sleep(0.05)
            continue
        times += 1
        if color_changed(base_color_orange, color_exist, tolerance=100) and times >= 3:
            total_time = time.time() - fishing_start_time
            sys.stdout.flush()
            safe_log(f"🐟上鱼咯ヾ(✿ﾟ▽ﾟ），耗时 {total_time:.2f} 秒")  # ← 打印结果
            
            left_up()
            break
        left_down()
        time.sleep(0.6)
        try:
            color_exist = get_pointer_color(CHECK_X, CHECK_Y)
        except Exception:
            pass
        if color_changed(base_color_orange, color_exist, tolerance=100) and times >= 3:
            left_up()
            break
        left_up()
        time.sleep(0.3)


# 新增颜色检测函数
def is_cast_successful_by_color(frame, window_w, window_h, rel_roi, target_bgr, tolerance=50.0):
    """
    判断当前帧中指定 ROI 的平均颜色是否接近目标颜色（抛竿成功标志）
    :param frame: BGR 图像 (H, W, 3)
    :param window_w, window_h: 窗口宽高
    :param rel_roi: (rel_x, rel_y, rel_w, rel_h)
    :param target_bgr: 目标 BGR 均值，如 [41.6, 186.9, 249.6]
    :param tolerance: 颜色欧氏距离容忍度
    :return: bool
    """
    rel_x, rel_y, rel_w, rel_h = rel_roi
    x = int(rel_x * window_w)
    y = int(rel_y * window_h)
    w = int(rel_w * window_w)
    h = int(rel_h * window_h)

    # 边界保护
    if w <= 0 or h <= 0 or x + w > frame.shape[1] or y + h > frame.shape[0]:
        print("⚠️ ROI 越界，跳过颜色检测")
        return False

    roi = frame[y:y+h, x:x+w]
    if roi.size == 0:
        return False

    mean_bgr = cv2.mean(roi)[:3]  # (B, G, R)
    mean_bgr = np.array(mean_bgr, dtype=np.float32)

    # 计算欧氏距离
    dist = np.linalg.norm(mean_bgr - target_bgr)
    # print(f"📏 颜色距离: {dist:.2f} (阈值: {tolerance})")

    return dist <= tolerance

def auto_fish_once():
    # === 第一步：在抛竿前，立即抓取"干净"画面作为基准 ===
    with mss.mss() as sct:
        region = {"top": window_top, "left": window_left, "width": window_width, "height": window_height}
        screenshot = sct.grab(region)
        pre_cast_frame = np.array(screenshot)[:, :, :3]

    # 初始化F按钮检测器
    fbutton_trigger = FButtonChangeTrigger(
        threshold=0.85,      # 相似度阈值（可调整）
        min_consecutive=2,    # 连续2帧未变化
        interval=0.2          # 检测间隔
    )
    
    if not fbutton_trigger.set_base(pre_cast_frame, window_width, window_height):
        print("⚠️ F按钮基准图设置失败！")

    # === 第二步：执行抛竿 ===
    time.sleep(0.1)
    fishing_start_time = time.time() #总计时
    left_down()
    print("🎣 抛竿中...")

    # === 第三步：抛竿后检测F按钮区域（等待抛竿动画）===
    time.sleep(1.0)  # 等待抛竿动画完成
    
    bucket_full_detected = False
    check_start = time.time()
    
    # 检测几帧，确认F按钮区域是否变化
    for _ in range(5):  # 最多检测5帧
        with mss.mss() as sct:
            screenshot = sct.grab({"top": window_top, "left": window_left, "width": window_width, "height": window_height})
            frame = np.array(screenshot)[:, :, :3]

        is_full, sim = fbutton_trigger.check_bucket_full(frame, window_width, window_height)
        if is_full:
            bucket_full_detected = True
            break
        time.sleep(0.1)

    if bucket_full_detected:
        left_up()
        return handle_bucket_full()

    # ──────────────── 继续正常钓鱼流程 ────────────────
    # 等待抛竿完全结束
    time.sleep(random.uniform(1.0, 1.5))

    try:
        pyautogui.keyDown('a')
        time.sleep(0.05)
        pyautogui.keyUp('a')
    except Exception as e:
        print("A键按压异常:", e)

    left_up()
 

    # 后续咬钩、收杆逻辑不变...
    status = enhanced_bite_check(fishing_start_time, fbutton_trigger, pre_cast_frame)
    if not status:
        print("⏳ 钓鱼超时或抛竿失败，正在重整方向...")
        try:
            pyautogui.press('w')
            time.sleep(3)
            print("✅ 方向重整完成，准备下一轮钓鱼")
        except Exception as e:
            print(f"⚠️ W键操作异常: {e}")
        return "timeout"

    reel(fishing_start_time)
    time.sleep(random.uniform(1.5, 2.5))
    left_click()
    detect_star_quality()
    time.sleep(1)
    return "success"


def handle_bucket_full():
    """统一处理鱼桶满的逻辑"""
    print("🐟 鱼桶已满，停止钓鱼！等待60秒后重试...")
    play_bucket_full_wav()
    time.sleep(0.5)
    left_down()          # 按下左键（你已定义的函数）
    time.sleep(5)       # 持续按住 10 秒
    left_up()            # 松开左键
    time.sleep(6)
    

    try:
        legendary_count = star_quality_count.get("传奇", 0)
        epic_count = star_quality_count.get("史诗", 0)
        rare_count = star_quality_count.get("稀有", 0)
        if legendary_count > 0:
           
            play_sound("ouhuang.wav")
        elif rare_count > 0 or epic_count > 0:
            
            play_sound("huiben.wav")
        else:
            
            play_sound("dawo.wav")
    except Exception as e:
        print(f"播放品质音效失败: {e}")

    time.sleep(60)
    return "bucket_full"

# ====== 新增：GUI 日志窗口模块 ======
import tkinter as tk
from PIL import Image, ImageTk
import threading
import queue
import win32gui
import win32con
import win32api


def listen_for_exit():
    keyboard.wait('f2')
    print("\n[EXIT] F2 pressed. Shutting down...")
    os._exit(0)

# 启动退出监听器
threading.Thread(target=listen_for_exit, daemon=True).start()

TRANSCOLOUR = 'white'

class LogWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🦊 Vicksy")
        # 去掉标题栏和边框
        self.root.overrideredirect(True)
        self.root.geometry("258x450")
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSCOLOUR)
        self.root.wm_attributes("-transparentcolor", TRANSCOLOUR)
        # 支持窗口拖动
        self.root.bind("<ButtonPress-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)

        # === 加载带透明通道图片 ===
        try:
            img_path = resource_path("vicksy_fishing.png")
            image = Image.open(img_path).convert("RGBA")
            # 缩放
            target_width = 200
            ratio = target_width / float(image.size[0])
            target_height = int(float(image.size[1]) * ratio)
            resized_image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            # 贴到白色背景以便透明色统一
            background = Image.new("RGB", resized_image.size, (255, 255, 255))
            if resized_image.mode == 'RGBA':
                background.paste(resized_image, mask=resized_image.split()[-1])
            else:
                background.paste(resized_image)
            self.photo = ImageTk.PhotoImage(background)
            self.img_label = tk.Label(self.root, image=self.photo, bg=TRANSCOLOUR)
            self.img_label.pack(pady=5)
        except Exception as e:
            print(f"图片加载失败: {e}")
            fallback = tk.Label(
                self.root,
                text="🦊",
                bg=TRANSCOLOUR,
                fg='lime',
                font=("Arial", 24)
            )
            fallback.pack(pady=20)

        # ====== 日志样式及字体查找 ======
        LOG_BG_COLOUR = 'white'
        LOG_FONT_COLOUR = 'black'
        FONT_CHOICES = [
            'Segoe UI Mono',
            'Consolas',
            'Courier New',
            'DejaVu Sans Mono',
        ]
        def find_available_font(font_list):
            for font_name in font_list:
                try:
                    tk.font.Font(family=font_name, size=10)
                    return font_name
                except Exception:
                    continue
            return 'TkDefaultFont'
        LOG_FONT_FAMILY = find_available_font(FONT_CHOICES)
        LOG_FONT_SIZE = 10
        LOG_HEIGHT = 2

        self.text_widget = tk.Text(
            self.root,
            bg='black',
            fg='yellow',
            font=(LOG_FONT_FAMILY, LOG_FONT_SIZE),
            height=LOG_HEIGHT,
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.text_widget.pack(fill=tk.X, padx=5, pady=(0, 5))

        # === Emoji 彩色统计状态栏 ===
        self.stats_text = tk.Text(
            self.root,
            height=1,
            bg='black',
            fg='yellow',
            font=(LOG_FONT_FAMILY, 12),
            wrap=tk.NONE,
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=5,
            pady=2
        )
        self.stats_text.pack(fill=tk.X, padx=5, pady=(0, 5))

       # === ✅ 新增：状态提示栏（F1/F2 + 指示灯）===
        self.status_text = tk.Text(
            self.root,
            height=1,
            bg='black',
            fg='yellow',
            font=("微软雅黑", 10),
            wrap=tk.NONE,
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=5,
            pady=2
        )
        self.status_text.pack(fill=tk.X, padx=5, pady=(0, 5))

        # 配置 tags
        self.status_text.tag_configure("indicator", foreground="red")
        self.status_text.tag_configure("f1", foreground="cyan")
        self.status_text.tag_configure("f2", foreground="orange")
        self.status_text.tag_configure("paused", foreground="red")
        self.status_text.tag_configure("running", foreground="green")



        # 品质 -> Emoji 映射
        self.quality_symbols = {
        "标准": "●",
        "非凡": "●",
        "稀有": "●",
        "史诗": "●",
        "传奇": "●"
        }

        # 品质 -> 颜色（用于高亮数字）
        self.quality_colors = {
            "标准": "#C0C0C0",
            "非凡": "#60C65A",
            "稀有": "#70AEF1",
            "史诗": "#AB66FB",
            "传奇": "#F8C544"
        }

        # 配置 tags
        self.stats_text.tag_configure("total", foreground="yellow")
        for q in self.quality_symbols:
            self.stats_text.tag_configure(q, foreground=self.quality_colors[q])

        # 初始化显示
        self._update_stats_display()
        self._update_status_display()
        # 关闭按钮
        close_btn = tk.Button(
            self.root,
            text="×",
            command=self.root.destroy,
            bg=TRANSCOLOUR,
            fg='red',
            font=("Arial", 20, "bold"),
            bd=0,
            highlightthickness=0,
            width=2
        )
        close_btn.place(relx=1.0, rely=0.0, anchor='ne')

        # === 日志队列等 ===
        self.log_queue = queue.Queue()
        self.running = True
        self.update_logs()

    def log(self, message):
        self.log_queue.put(str(message))

    def update_logs(self):
        MAX_LINES = 2  # 最多保留 4 行日志
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.text_widget.config(state=tk.NORMAL)
            
            # 插入新消息
            self.text_widget.insert(tk.END, msg + "\n")
            
            # 获取总行数
            line_count = int(self.text_widget.index('end-1c').split('.')[0])
            
            # 如果超过 MAX_LINES，删除最上面的行
            while line_count > MAX_LINES:
                self.text_widget.delete(1.0, "2.0")  # 删除第一行（包括换行符）
                line_count -= 1
            
            self.text_widget.config(state=tk.DISABLED)
        
        if self.running:
            self.root.after(100, self.update_logs)

    def run(self):
        self.root.mainloop()

    def stop(self):
        self.running = False

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def _update_stats_display(self):
        total = sum(star_quality_count.values())
        
        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)

        # 🎣 总数（白色）
        self.stats_text.insert(tk.END, f"🎣{total} | ", "total")

        # 各品质：彩色 ● + 数字（同色）
        for quality in ["标准", "非凡", "稀有", "史诗", "传奇"]:
            symbol = self.quality_symbols[quality]
            count = star_quality_count[quality]
            self.stats_text.insert(tk.END, symbol, quality)
            self.stats_text.insert(tk.END, f"{count} ", quality)

        self.stats_text.config(state=tk.DISABLED)

        

    def _update_status_display(self):
        global fishing_paused
        
        indicator_symbol = "🔴" if fishing_paused else "🟢"
        indicator_tag = "paused" if fishing_paused else "running"

        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        
        # 插入带颜色的指示灯 + 文字
        self.status_text.insert(tk.END, indicator_symbol, indicator_tag)
        self.status_text.insert(tk.END, " F1: 开关 | F2: 退出")
        
        self.status_text.config(state=tk.DISABLED)   

 

# ====== 8. 主循环入口 ======
# ====== 全局钓鱼控制开关 ======
log_window = None
global fishing_paused

def update_stats(self, total=0, standard=0, extraordinary=0, rare=0, epic=0, legendary=0):
    """更新钓鱼统计显示"""
    text = f"共钓 {total} 条：{standard} 标准，{extraordinary} 非凡，{rare} 稀有，{epic} 史诗，{legendary} 传奇"
    self.stats_label.config(text=text)

def safe_log(msg):
    """安全日志函数，避免 GUI 未初始化时报错"""
    if 'log_window' in globals() and log_window:
        log_window.log(msg)
    else:
        print(msg)


class PrintRedirector:
    def __init__(self):
        self.line_buffer = ""

    def write(self, message):
        if message.strip() == "":
            return
        self.line_buffer += message
        # 处理换行（print 默认带 \n）
        while "\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\n", 1)
            if line.strip():
                safe_log(line)

    def flush(self):
        # 如果有残余内容（无换行结尾），也输出
        if self.line_buffer.strip():
            safe_log(self.line_buffer.strip())
            self.line_buffer = ""
# ====== 主程序入口 ======
if __name__ == "__main__":
    # === 1. 初始化全局状态（必须在 LogWindow 创建前定义！）===
    global fishing_paused
    fishing_paused = True  # 默认暂停

    # === 2. 创建日志窗口 ===
    log_window = LogWindow()

    # 重定向 print
    sys.stdout = PrintRedirector()
    sys.stderr = PrintRedirector()

    safe_log("🦊 狐狐附身...")
    safe_log("✅ 按 F1 开始/暂停自动钓鱼")
    safe_log("请将窗口切回至猛兽派对...")
    safe_log(f"游戏窗口分辨率: {window_width}x{window_height}")
    safe_log("面朝小河，拿起鱼竿，准备好钓饵     按 F1 请🦊狐狐附身钓鱼")

    time.sleep(1)

    # ✅ 注册 F1 热键
    def toggle_fishing(e=None):
        global fishing_paused
        fishing_paused = not fishing_paused
        status = "⏸ 已暂停" if fishing_paused else "▶ 钓鱼中..."
        safe_log(status)
        if log_window:
            log_window._update_status_display()

    keyboard.add_hotkey('F1', toggle_fishing)

    # F2 退出已在 listen_for_exit 中处理

    # === 3. 启动钓鱼线程 ===
    def run_fishing_loop():
        global fishing_paused
        bucket_full_retry_count = 0
        max_bucket_full_retries = 5
        try:
            while True:
                if fishing_paused:
                    time.sleep(0.2)
                    continue
                result = auto_fish_once()
                if result == "bucket_full":
                    bucket_full_retry_count += 1
                    if bucket_full_retry_count >= max_bucket_full_retries:
                        safe_log("多次检测到鱼桶满，程序停止")
                        break
                    safe_log(f"鱼桶满检测次数: {bucket_full_retry_count}/{max_bucket_full_retries}")
                else:
                    bucket_full_retry_count = 0
                time.sleep(0.5)
        except Exception as e:
            error_msg = f"❌ 运行出错:\n{traceback.format_exc()}"
            safe_log(error_msg)

    fishing_thread = threading.Thread(target=run_fishing_loop, daemon=True)
    fishing_thread.start()

    # === 4. 启动 GUI ===
    try:
        log_window.run()
    except KeyboardInterrupt:
        pass
    finally:
        log_window.stop()