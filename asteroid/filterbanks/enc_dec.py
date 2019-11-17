"""
Base classes for filterbanks, encoders and decoders.
@author : Manuel Pariente, Inria-Nancy
"""

from torch.nn import functional as F

from ..engine.sub_module import SubModule
from . inputs_and_masks import _inputs, _masks


class Filterbank(SubModule):
    """Base Filterbank class.
    Each subclass has to implement a `filters` property.

    # Args
        n_filters: Positive int. Number of filters.
        kernel_size: Positive int. Length of the filters.
        stride: Positive int. Stride of the conv or transposed conv. (Hop size).
            If None (default), set to `kernel_size // 2`.
    """
    def __init__(self, n_filters, kernel_size, stride=None):
        super(Filterbank, self).__init__()
        self.n_filters = n_filters
        self.kernel_size = kernel_size
        self.stride = stride if stride else self.kernel_size // 2

    @property
    def filters(self):
        """ Abstract method for filters. """
        raise NotImplementedError

    def get_config(self):
        """ Returns dictionary of arguments to re-instantiate the class."""
        config = {
            'n_filters': self.n_filters,
            'kernel_size': self.kernel_size,
            'stride': self.stride
        }
        return config


class Encoder(SubModule):
    """ Encoder class. Add encoding methods to Filterbank classes.
    Not intended to be subclassed.

    Args:
        filterbank: (subclass of) Filterbank instance. The filterbank to use
            as an encoder.
        inp_mode: String. One of [`'reim'`, `'mag'`, `'cat'`]. Controls
            `post_processing_inputs` method which can be applied after
            the forward.
            - `'reim'` or `'real'` corresponds to the concatenation of
                real and imaginary parts. (filterbank seen as real-valued).
            - `'mag'` or `'mod'`corresponds to the magnitude (or modulus)of the
                complex filterbank output.
            - `'cat'` or `'concat'` corresponds to the concatenation of both
                previous representations.
        mask_mode: String. One of [`'reim'`, `'mag'`, `'comp'`]. Controls
            the way the time-frequency mask is applied to the input
            representation in the `apply_mask` method.
            - `'reim'` or `'real'` corresponds to a real-valued filterbank
                where both the input and the mask consists in the
                concatenation of real and imaginary parts.
            - `'mag'` or `'mod'`corresponds to a magnitude (or modulus) mask
                applied to the complex filterbank output.
            - `'comp'` or `'complex'` corresponds to a complex mask : the
                input and the mask are point-wise multiplied in the complex
                sense.
    """
    def __init__(self, filterbank, inp_mode='reim', mask_mode='reim'):
        super(Encoder, self).__init__()
        self.inp_mode = inp_mode
        self.mask_mode = mask_mode

        self.filterbank = filterbank
        self.filters = self.filterbank.filters
        self.stride = self.filterbank.stride

        self.inp_func, self.in_chan_mul = _inputs[self.inp_mode]
        self.mask_func, self.out_chan_mul = _masks[self.mask_mode]

    def forward(self, waveform):
        """ Convolve 1D torch.Tensor with filterbank."""
        return F.conv1d(waveform, self.filters, stride=self.stride)

    def post_process_inputs(self, x):
        """ Computes real or complex representation from `forward` output."""
        return self.inp_func(x)

    def apply_mask(self, tf_rep, mask, dim=1):
        """ Applies real of complex masks `forward` output. """
        return self.mask_func(tf_rep, mask, dim=dim)

    def get_config(self):
        """ Returns dictionary of arguments to re-instantiate the class."""
        config = {
            'inp_mode': self.inp_mode,
            'mask_mode': self.mask_mode
        }
        base_config = self.filterbank.get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Decoder(SubModule):
    """Decoder class. Add decoding methods to Filterbank classes.
    Not intended to be subclassed.
    Args:
        filterbank: (subclass of) Filterbank instance. The filterbank to use
            as an decoder.
    """
    def __init__(self, filterbank):
        super(Decoder, self).__init__()

        self.filterbank = filterbank
        self.filters = self.filterbank.filters
        self.stride = self.filterbank.stride

    def forward(self, spec):
        """
        Applies transposed convolution to a TF representation. This is
        equivalent to overlap-add.
        Args:
            spec: 3D or 4D torch.Tensor. The TF representation.
                (Output of `Encoder.forward`).
        Returns:
            torch.Tensor, the corresponding time domain signal.
        """
        if len(spec.shape) == 3:
            return F.conv_transpose1d(spec, self.filters, stride=self.stride)
        elif len(spec.shape) == 4:
            batch, n_src, chan, spec_len = spec.shape
            out = F.conv_transpose1d(spec.view(batch * n_src, chan, spec_len),
                                     self.filters, stride=self.stride)
            return out.view(batch, n_src, -1)

    def get_config(self):
        return self.filterbank.get_config()


class NoEncoder(SubModule):
    """ Class to use for no neural encoder, i.e this is a placeholder for
    precomputed features.
    The features can be complex with real and imaginary parts concatenated
    into the same axis. The same post processing and masking strategies are
    available as for the `Encoder` class.

    Args:
        inp_mode: String. One of [`'reim'`, `'mag'`, `'cat'`]. Controls
            `post_processing_inputs` method which can be applied after
            the forward.
            - `'reim'` or `'real'` corresponds to the concatenation of
                real and imaginary parts. (filterbank seen as real-valued).
            - `'mag'` or `'mod'`corresponds to the magnitude (or modulus)of the
                complex filterbank output.
            - `'cat'` or `'concat'` corresponds to the concatenation of both
                previous representations.
        mask_mode: String. One of [`'reim'`, `'mag'`, `'comp'`]. Controls
            the way the time-frequency mask is applied to the input
            representation in the `apply_mask` method.
            - `'reim'` or `'real'` corresponds to a real-valued filterbank
                where both the input and the mask consists in the
                concatenation of real and imaginary parts.
            - `'mag'` or `'mod'`corresponds to a magnitude (or modulus) mask
                applied to the complex filterbank output.
            - `'comp'` or `'complex'` corresponds to a complex mask : the
                input and the mask are point-wise multiplied in the complex
                sense.
    """
    def __init__(self, inp_mode='reim', mask_mode='reim'):

        super(NoEncoder, self).__init__()
        self.inp_mode = inp_mode
        self.mask_mode = mask_mode

        self.inp_func, self.in_chan_mul = _inputs[self.inp_mode]
        self.mask_func, self.out_chan_mul = _masks[self.mask_mode]

    def forward(self, features):
        return features

    def post_process_inputs(self, x):
        return self.inp_func(x)

    def apply_mask(self, tf_rep, mask, dim=1):
        return self.mask_func(tf_rep, mask, dim=dim)

    def get_config(self):
        """ Returns dictionary of arguments to re-instantiate the class."""
        config = {
            'inp_mode': self.inp_mode,
            'mask_mode': self.mask_mode
        }
        return config
