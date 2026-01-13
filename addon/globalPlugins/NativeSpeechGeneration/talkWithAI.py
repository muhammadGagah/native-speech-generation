# -*- coding: utf-8 -*-
import wx
import sys
import threading
import asyncio
import traceback
import gui
from logHandler import log
import addonHandler

import os
import winsound
import queue
addonHandler.initTranslation()

# Ensure lib directory is in path
addon_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(addon_dir, "lib")
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

# Optional imports handled gracefully
try:
    import pyaudio
except ImportError:
    pyaudio = None
    log.warning("talkWithAI: PyAudio not found.")

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    log.warning("talkWithAI: Google GenAI not found.")


# Constants
MODEL_NAME = "gemini-2.5-flash-native-audio-preview-12-2025"
MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
STREAM_START_SOUND_PATH = os.path.join(MEDIA_DIR, "stream-start.wav")
STREAM_END_SOUND_PATH = os.path.join(MEDIA_DIR, "stream-end.wav")

# Audio Format Constants
FORMAT = pyaudio.paInt16 if pyaudio else 8
CHANNELS = 1
INPUT_RATE = 16000  # Standard for speech recognition / input
OUTPUT_RATE = 24000 # Standard for Gemini Live output
CHUNK = 1024 # Larger chunk to reduce CPU/Network overhead
BUFFER_THRESHOLD = 5 # Lower buffer for faster response (approx 0.2s)

import struct

class TalkWithAIDialog(wx.Dialog):
    def __init__(self, parent, api_key, voice_name, system_instruction):
        super().__init__(parent, title=_("Talk With AI"), size=(400, 300))
        self.api_key = api_key
        self.voice_name = voice_name
        self.system_instruction = system_instruction
        
        self.client = None
        self.session_active = False
        self.loop = None
        self.loop_thread = None
        self.audio_interface = None
        self.input_stream = None
        self.output_stream = None
        self.mic_on = True
        
        self.audio_queue = queue.Queue()
        self.is_playing = False
        self.play_thread = None
        self.volume = 80 # Default volume percentage
        
        # Audio Device Selection
        self.input_devices = self._get_device_list(input=True)
        self.output_devices = self._get_device_list(input=False)
        self.selected_input_idx = None
        self.selected_output_idx = None

        self._build_ui()
        
        if not pyaudio:
            wx.CallAfter(self.report_error, _("PyAudio library is not installed. This feature requires PyAudio."))
            self.connect_btn.Disable()
        if not genai:
            wx.CallAfter(self.report_error, _("Google GenAI library is not installed."))
            self.connect_btn.Disable()

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)

    def _get_device_list(self, input=True):
        """Returns a list of dicts: {'index': int, 'name': str}"""
        devices = []
        if not pyaudio:
             return devices
        p = pyaudio.PyAudio()
        try:
            info = p.get_host_api_info_by_index(0)
            num_devices = info.get('deviceCount')
            for i in range(num_devices):
                dev = p.get_device_info_by_host_api_device_index(0, i)
                if input:
                    if dev.get('maxInputChannels') > 0:
                         devices.append({'index': i, 'name': dev.get('name')})
                else:
                    if dev.get('maxOutputChannels') > 0:
                         devices.append({'index': i, 'name': dev.get('name')})
        except Exception as e:
            log.error(f"Error listing devices: {e}")
        finally:
            p.terminate()
        return devices


    def _build_ui(self):
        # Main Sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.Panel(self)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 1. Status Area
        status_box = wx.StaticBox(panel, label=_("Status"))
        status_sizer = wx.StaticBoxSizer(status_box, wx.VERTICAL)
        self.status_label = wx.StaticText(panel, label=_("Ready to Connect"))
        status_sizer.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 5)
        panel_sizer.Add(status_sizer, 0, wx.ALL | wx.EXPAND, 5)

        # 2. Controls Area
        controls_box = wx.StaticBox(panel, label=_("Controls"))
        controls_sizer = wx.StaticBoxSizer(controls_box, wx.VERTICAL)
        
        # Connect/Disconnect Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.connect_btn = wx.Button(panel, label=_("Start Conversation"))
        self.connect_btn.Bind(wx.EVT_BUTTON, self.on_connect)
        self.disconnect_btn = wx.Button(panel, label=_("Stop Conversation"))
        self.disconnect_btn.Bind(wx.EVT_BUTTON, self.on_disconnect)
        self.disconnect_btn.Disable()
        
        btn_sizer.Add(self.connect_btn, 1, wx.RIGHT, 5)
        btn_sizer.Add(self.disconnect_btn, 1, wx.LEFT, 5)
        controls_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.mic_btn = wx.ToggleButton(panel, label=_("Microphone: ON"))
        self.mic_btn.SetValue(True)
        self.mic_btn.Bind(wx.EVT_TOGGLEBUTTON, self.on_mic_toggle)
        controls_sizer.Add(self.mic_btn, 0, wx.ALL | wx.EXPAND, 5)

        # Device Selection Sizer
        self.device_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Input Device
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        input_label = wx.StaticText(panel, label=_("Microphone:"))
        input_choices = [d['name'] for d in self.input_devices]
        self.input_choice = wx.Choice(panel, choices=input_choices)
        if input_choices:
             self.input_choice.SetSelection(0)
        input_sizer.Add(input_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        input_sizer.Add(self.input_choice, 1, wx.EXPAND)
        self.device_sizer.Add(input_sizer, 0, wx.ALL | wx.EXPAND, 5)

        # Output Device
        output_sizer = wx.BoxSizer(wx.HORIZONTAL)
        output_label = wx.StaticText(panel, label=_("Speaker:"))
        output_choices = [d['name'] for d in self.output_devices]
        self.output_choice = wx.Choice(panel, choices=output_choices)
        if output_choices:
             self.output_choice.SetSelection(0)
        output_sizer.Add(output_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        output_sizer.Add(self.output_choice, 1, wx.EXPAND)
        self.device_sizer.Add(output_sizer, 0, wx.ALL | wx.EXPAND, 5)
        
        controls_sizer.Add(self.device_sizer, 0, wx.EXPAND)

        # Google Search Checkbox
        self.google_search_cb = wx.CheckBox(panel, label=_("Grounding with Google Search"))
        self.google_search_cb.SetValue(False)
        controls_sizer.Add(self.google_search_cb, 0, wx.ALL | wx.EXPAND, 5)
        
        # Volume Slider
        vol_sizer = wx.BoxSizer(wx.HORIZONTAL)
        vol_label = wx.StaticText(panel, label=_("Volume:"))
        self.vol_slider = wx.Slider(panel, value=self.volume, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
        self.vol_slider.Bind(wx.EVT_SLIDER, self.on_volume_change)
        
        vol_sizer.Add(vol_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        vol_sizer.Add(self.vol_slider, 1, wx.EXPAND)
        controls_sizer.Add(vol_sizer, 0, wx.ALL | wx.EXPAND, 5)

        panel_sizer.Add(controls_sizer, 0, wx.ALL | wx.EXPAND, 5)

        # 3. Info Area (Voice only)
        # Translators: Label for the selected voice
        info_label = wx.StaticText(panel, label=_("Voice: ") + str(self.voice_name))
        panel_sizer.Add(info_label, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)

        panel.SetSizer(panel_sizer)
        main_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(main_sizer)
        self.CenterOnParent()
        
    def update_status(self, text):
        if self:
            self.status_label.SetLabel(_("Status: ") + text)

    def report_error(self, msg):
        if self:
            wx.MessageBox(str(msg), _("Error"), wx.OK | wx.ICON_ERROR)
            self.update_status(_("Error"))

    def on_mic_toggle(self, evt):
        self.mic_on = self.mic_btn.GetValue()
        label = _("Microphone: ON") if self.mic_on else _("Microphone: OFF")
        self.mic_btn.SetLabel(label)

    def on_volume_change(self, evt):
        self.volume = self.vol_slider.GetValue()

    def on_connect(self, evt):
        self.connect_btn.Disable()
        self.disconnect_btn.Enable()
        
        # Store state and hide checkbox & device selection
        self.use_google_search = self.google_search_cb.GetValue()
        self.google_search_cb.Hide()
        
        # Get selected devices
        in_sel = self.input_choice.GetSelection()
        if in_sel != wx.NOT_FOUND and self.input_devices:
             self.selected_input_idx = self.input_devices[in_sel]['index']
        
        out_sel = self.output_choice.GetSelection()
        if out_sel != wx.NOT_FOUND and self.output_devices:
             self.selected_output_idx = self.output_devices[out_sel]['index']

        # Hide device selection by hiding their sizer items provided the sizer exists
        # Actually easier to hide the controls
        self.input_choice.Hide()
        self.output_choice.Hide()
        # To truly hide the space, we might need to detach or hide via sizer but simple Hide() usually works well enough in wx
        # A cleaner way is to Hide the sizer or panel area
        # Let's verify if hiding controls collapses layout
        # We can recursively hide the static texts too if we want, but let's keep it simple first. 
        # Better: Hide list controls, maybe the labels too.
        # Let's hide the whole device_sizer content manually or if we put it in a panel.
        # For now, just hiding choices is requested, but labels should probably go too.
        # Let's use ShowItems on sizer if possible or just loop
        for child in self.device_sizer.GetChildren():
            w = child.GetWindow()
            if w: w.Hide()
            s = child.GetSizer()
            if s: 
                for c in s.GetChildren():
                     w2 = c.GetWindow()
                     if w2: w2.Hide()

        self.Layout()
        
        self.update_status(_("Connecting..."))
        
        self.session_active = True
        self.loop_thread = threading.Thread(target=self._start_async_loop, daemon=True)
        self.loop_thread.start()

    def on_disconnect(self, evt):
        self.disconnect_btn.Disable()
        self.update_status(_("Disconnecting..."))
        # Sound is played in run_session finally block
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.cleanup_async(), self.loop)

    def _play_sound_effect(self, path):
        """Plays a local sound file asynchronously."""
        def _bg_play():
            try:
                if os.path.exists(path):
                     winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass

        threading.Thread(target=_bg_play, daemon=True).start()

    def on_char_hook(self, evt):
        if evt.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
        else:
            evt.Skip()

    def on_close(self, evt: wx.Event):
        self.session_active = False
        self.is_playing = False
        
        # Drain and clear audio queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
        self.audio_queue.put(b"")

        if self.loop and self.loop.is_running():
            try:
                # Schedule cleanup and wait for it
                future = asyncio.run_coroutine_threadsafe(self.cleanup_async(), self.loop)
                # Wait briefly for cleanup to run
                try:
                    future.result(timeout=2.0)
                except Exception:
                    pass
                
                # Signal loop to stop
                self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception:
                pass
        
        if self.audio_interface:
            try:
                self.audio_interface.terminate()
            except:
                pass
            
        self.Destroy()


    def _start_async_loop(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.run_session())
        except RuntimeError:
            # Loop stopped cleanly or forcefully
            pass
        except Exception as e:
            log.error(f"Async Loop Error: {e}", exc_info=True)
        finally:
            try:
                # Cancel all remaining tasks specific to this loop
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                
                # Allow cancellations to process
                if pending and not self.loop.is_closed():
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                if not self.loop.is_closed():
                    self.loop.close()
            except Exception:
                pass

    async def cleanup_async(self):
        self.session_active = False
        self.is_playing = False
        
        # Cancel all tasks in the current loop to force exits
        current_task = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is not current_task:
                task.cancel()

        # Drain queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except:
                pass
                
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
            self.input_stream = None
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None
        if self.audio_interface:
            self.audio_interface.terminate()
            self.audio_interface = None

    def _audio_player_worker(self):
        """
        Thread that consumes audio chunks from the queue, applies volume, and plays them.
        """
        buffer = []
        buffering = True

        while self.session_active and self.is_playing:
            try:
                # Wait for data
                data = self.audio_queue.get(timeout=0.1)
                
                # Apply Volume
                if self.volume != 100:
                    # Parse 16-bit PCM (signed)
                    count = len(data) // 2
                    shorts = struct.unpack(f"{count}h", data)
                    
                    # Apply scale factor (0.0 to 1.0)
                    factor = self.volume / 100.0
                    
                    # Scale and clip
                    scaled_shorts = []
                    for s in shorts:
                        val = int(s * factor)
                        # Clip to 16-bit range
                        if val > 32767: val = 32767
                        if val < -32768: val = -32768
                        scaled_shorts.append(val)
                    
                    data = struct.pack(f"{count}h", *scaled_shorts)

                if buffering:
                    buffer.append(data)
                    if len(buffer) >= BUFFER_THRESHOLD:
                        buffering = False
                        # Play accumulated buffer
                        if self.output_stream and self.output_stream.is_active():
                            for chunk in buffer:
                                self.output_stream.write(chunk)
                        buffer = []
                else:
                    # Direct play
                    if self.output_stream and self.output_stream.is_active():
                        self.output_stream.write(data)
                        
            except queue.Empty:
                # If queue is empty, we have run out of audio data.
                # To prevent micro-stuttering, we switch back to buffering mode.
                if not buffering and self.session_active:
                     buffering = True
                continue
            except Exception as e:
                log.error(f"Audio Player Error: {e}")
                break

    async def send_audio_loop(self, session):
        while self.session_active:
            if self.mic_on and self.input_stream and self.input_stream.is_active():
                try:
                    data = await self.loop.run_in_executor(
                        None, 
                        lambda: self.input_stream.read(CHUNK, exception_on_overflow=False)
                    )
                    await session.send(input={"data": data, "mime_type": f"audio/pcm;rate={INPUT_RATE}"}, end_of_turn=False)
                except Exception as e:
                    log.error(f"Mic/Send Error: {e}")
                    break
            else:
                await asyncio.sleep(0.1)

    async def receive_loop(self, session):
        try:
            async for response in session.receive():
                if not self.session_active:
                    break
                
                if response.server_content is None:
                    continue

                # Handle Interruption
                if response.server_content.interrupted:
                    log.debug("TalkWithAI: Server Interrupted")
                    # Clear audio queue to stop playing immediately
                    # This prevents "echo" loop where model hears its own delayed speech
                    while not self.audio_queue.empty():
                        try:
                            self.audio_queue.get_nowait()
                        except queue.Empty:
                            break
                    continue

                # Handle Turn Complete
                if response.server_content.turn_complete:
                    log.debug("TalkWithAI: Turn Complete")
                    continue

                model_turn = response.server_content.model_turn
                if model_turn is not None:
                    for part in model_turn.parts:
                        if part.inline_data is not None:
                            audio_data = part.inline_data.data
                            # Push to queue instead of writing directly
                            self.audio_queue.put(audio_data)
        except Exception as e:
            log.error(f"TalkWithAI Receive Loop Error: {e}")
        finally:
            log.debug("TalkWithAI: Receive loop ended")
            # Do NOT set self.session_active = False here.
            # Doing so would stop the reconnection loop in run_session.

    async def run_session(self):
        try:
            # Setup Audio (Once for the entire session duration)
            self.audio_interface = pyaudio.PyAudio()
            
            # Output Stream (Speaker)
            self.output_stream = self.audio_interface.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=OUTPUT_RATE,
                output=True,
                frames_per_buffer=CHUNK,
                output_device_index=self.selected_output_idx
            )
            
            # Input Stream (Mic)
            self.input_stream = self.audio_interface.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=INPUT_RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=self.selected_input_idx
            )
            
            # Initialize Client
            self.client = genai.Client(api_key=self.api_key, http_options={"api_version": "v1alpha"})
            
            # config object contains generation_config
            tools_config = []
            if self.use_google_search:
                tools_config.append({"google_search": {}})

            config = {
                "response_modalities": ["AUDIO"],
                "tools": tools_config,
                "generation_config": {
                   "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": self.voice_name
                            }
                        }
                    }
                },
                "system_instruction": {"parts": [{"text": self.system_instruction}]} if self.system_instruction else None
            }
            
            first_connect = True

            # Main Reconnection Loop
            while self.session_active:
                try:
                    log.debug("TalkWithAI: Connecting to Gemini Live...")
                    async with self.client.aio.live.connect(model=MODEL_NAME, config=config) as session:
                        if first_connect:
                             wx.CallAfter(self.update_status, _("Connected"))
                             # Play start sound only on the very first successful connection
                             self._play_sound_effect(STREAM_START_SOUND_PATH)
                             first_connect = False
                        else:
                             log.debug("TalkWithAI: Reconnected silently")
                        
                        self.session = session
                        
                        # Start sending and receiving tasks
                        send_task = asyncio.create_task(self.send_audio_loop(session))
                        receive_task = asyncio.create_task(self.receive_loop(session))
                        
                        if not self.is_playing:
                            play_worker = threading.Thread(target=self._audio_player_worker, daemon=True)
                            self.is_playing = True
                            play_worker.start()
                        
                        # Wait for either task to finish
                        # If connection drops, receive_loop finishes.
                        # We then cancel send_task and reconnect.
                        done, pending = await asyncio.wait(
                            [send_task, receive_task], 
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel pending tasks (e.g. send loop if receive died)
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                                
                except Exception as e:
                    log.error(f"TalkWithAI Session/Connection Error: {e}")
                    # Only play end sound if we are giving up (session not active)
                    # or just notify user of retry
                    wx.CallAfter(self.update_status, _("Connection Lost. Retrying..."))
                    await asyncio.sleep(2) # Backoff before reconnect
                
                if self.session_active:
                    log.debug("TalkWithAI: Reconnecting...")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"TalkWithAI Fatal Error: {traceback.format_exc()}")
            wx.CallAfter(self.report_error, str(e))
            self.session_active = False
        finally:
            # Play end sound only when completely stopping
            self._play_sound_effect(STREAM_END_SOUND_PATH)
            
            wx.CallAfter(self.reset_ui)
            # Cleanup Audio
            if self.input_stream:
                self.input_stream.stop_stream()
                self.input_stream.close()
                self.input_stream = None
            if self.output_stream:
                self.output_stream.stop_stream()
                self.output_stream.close()
                self.output_stream = None
            if self.audio_interface:
                self.audio_interface.terminate()
                self.audio_interface = None

    def reset_ui(self):
        if self:
            try:
                self.connect_btn.Enable()
                self.disconnect_btn.Disable()
                self.google_search_cb.Show()
                
                # Show device selection again
                for child in self.device_sizer.GetChildren():
                    w = child.GetWindow()
                    if w: w.Show()
                    s = child.GetSizer()
                    if s: 
                        for c in s.GetChildren():
                             w2 = c.GetWindow()
                             if w2: w2.Show()

                self.Layout()
                self.update_status(_("Ready"))
            except RuntimeError:
                pass # Window might be destroyed
