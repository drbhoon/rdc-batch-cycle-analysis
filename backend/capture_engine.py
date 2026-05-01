import cv2
import mss
import numpy as np
import time
import threading
import os

try:
    import pygetwindow as gw
except ImportError:
    gw = None
import os

class CaptureEngine:
    def __init__(self):
        self.is_recording = False
        self.output_filename = ""
        self.video_writer = None
        self.capture_thread = None
        self.fps = 5  # Low FPS is sufficient for UI state changes
        
    def _get_window_bbox(self, window_title="AnyDesk"):
        """Finds the window by title and returns its bounding box."""
        if gw is None:
            print("pygetwindow is not available on this platform.")
            return None
            
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                # Fallback: maybe it's just 'AnyDesk' or contains 'AnyDesk'
                all_windows = gw.getAllWindows()
                for w in all_windows:
                    if window_title.lower() in w.title.lower():
                        windows = [w]
                        break
                        
            if windows:
                win = windows[0]
                # Return the bounding box: (left, top, width, height)
                return {
                    "top": win.top, 
                    "left": win.left, 
                    "width": win.width, 
                    "height": win.height
                }
            return None
        except Exception as e:
            print(f"Error finding window: {e}")
            return None

    def start_recording(self, output_path="output.mp4", target_window="AnyDesk"):
        if self.is_recording:
            return False, "Already recording"
            
        if target_window == "Full Screen":
            with mss.mss() as sct:
                monitor = sct.monitors[1] # Primary monitor
                bbox = {
                    "top": monitor["top"],
                    "left": monitor["left"],
                    "width": monitor["width"],
                    "height": monitor["height"]
                }
        else:
            bbox = self._get_window_bbox(target_window)
            
        if not bbox:
            return False, f"Could not find window containing '{target_window}'"
            
        self.output_filename = output_path
        self.is_recording = True
        
        # Determine fourcc and initialize video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(
            self.output_filename, 
            fourcc, 
            self.fps, 
            (bbox["width"], bbox["height"])
        )
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self._capture_loop, args=(bbox,))
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
        return True, f"Started recording {target_window} to {output_path}"

    def _capture_loop(self, bbox):
        with mss.mss() as sct:
            frame_duration = 1.0 / self.fps
            while self.is_recording:
                start_time = time.time()
                
                # Capture the screen region
                sct_img = sct.grab(bbox)
                
                # Convert to numpy array and from BGRA to BGR
                frame = np.array(sct_img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                # Write to video
                if self.video_writer:
                    self.video_writer.write(frame)
                    
                # Sleep to maintain FPS
                elapsed = time.time() - start_time
                if elapsed < frame_duration:
                    time.sleep(frame_duration - elapsed)

    def stop_recording(self):
        if not self.is_recording:
            return False, "Not currently recording"
            
        self.is_recording = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
            
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            
        return True, f"Stopped recording. Saved to {self.output_filename}"
