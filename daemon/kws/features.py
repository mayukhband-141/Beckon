import numpy as np
from scipy.signal import get_window

class LogMelFeatureExtractor:
    """
    Zero-dependency Log-Mel Spectrogram feature extractor.
    Converts 16kHz audio slices into [n_mels, time_steps] acoustic tensors.
    Identical to standard Kaldi / Torchaudio MelSpectrogram DSP pipelines.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        n_fft: int = 512,
        win_length: int = 400,   # 25ms
        hop_length: int = 160,   # 10ms
        n_mels: int = 80,
        f_min: float = 80.0,
        f_max: float = 7600.0,
    ):
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.win_length = win_length
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.f_min = f_min
        self.f_max = f_max

        self.window = get_window("hann", win_length, fftbins=True).astype(np.float32)
        self.mel_filterbank = self._build_mel_filterbank()

    @staticmethod
    def _hz_to_mel(hz: float) -> float:
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    @staticmethod
    def _mel_to_hz(mel: float) -> float:
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    def _build_mel_filterbank(self) -> np.ndarray:
        """Constructs an [n_mels, n_fft // 2 + 1] triangular filterbank matrix."""
        min_mel = self._hz_to_mel(self.f_min)
        max_mel = self._hz_to_mel(self.f_max)
        mel_points = np.linspace(min_mel, max_mel, self.n_mels + 2)
        hz_points = self._mel_to_hz(mel_points)
        bins = np.floor((self.n_fft + 1) * hz_points / self.sample_rate).astype(int)

        num_fft_bins = self.n_fft // 2 + 1
        filterbank = np.zeros((self.n_mels, num_fft_bins), dtype=np.float32)

        for i in range(self.n_mels):
            left, center, right = bins[i], bins[i + 1], bins[i + 2]
            if center > left:
                filterbank[i, left:center] = (np.arange(left, center) - left) / (center - left)
            if right > center:
                filterbank[i, center:right] = (right - np.arange(center, right)) / (right - center)

        return filterbank

    def extract(self, audio: np.ndarray) -> np.ndarray:
        """
        Extracts Log-Mel Spectrogram features.
        Input: audio (1D float32 array, 16kHz)
        Output: features (2D float32 array [n_mels, time_steps])
        """
        if len(audio) < self.win_length:
            # Pad with silence if audio is too short
            padded = np.zeros(self.win_length, dtype=np.float32)
            padded[:len(audio)] = audio
            audio = padded

        # Frame audio with sliding window
        num_frames = 1 + (len(audio) - self.win_length) // self.hop_length
        if num_frames <= 0:
            return np.zeros((self.n_mels, 1), dtype=np.float32)

        # Vectorized frame slicing: [num_frames, win_length]
        shape = (num_frames, self.win_length)
        strides = (audio.strides[0] * self.hop_length, audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)

        # Apply Hann window
        windowed = frames * self.window

        # Compute Real FFT: [num_frames, n_fft // 2 + 1]
        fft_complex = np.fft.rfft(windowed, n=self.n_fft, axis=-1)
        power_spectrum = np.abs(fft_complex) ** 2.0

        # Apply Mel Filterbank: [num_frames, n_mels] -> Transpose to [n_mels, num_frames]
        mel_energy = np.matmul(power_spectrum, self.mel_filterbank.T)

        # Natural log compression with numerical stability
        log_mel = np.log(np.maximum(mel_energy, 1e-6)).T
        return log_mel.astype(np.float32)

