"""Models for DCGAN."""

import os

import torch
import torch.backends.cudnn as cudnn
import torch.nn as nn

from params import *
from utils import init_weights


class Discriminator(nn.Module):
    """Model for Discriminator."""

    def __init__(self, num_channels, conv_dim, image_size, num_gpu,
                 num_extra_layers, use_BN):
        """Init for Discriminator model."""
        super(Discriminator, self).__init__()
        assert image_size % 16 == 0, "image size must be a multiple of 16!"

        self.num_gpu = num_gpu
        self.layer = nn.Sequential()
        # input conv layer
        # input num_channels x image_size x image_size
        # output conv_dim x (image_size / 2) x (image_size / 2)
        self.layer.add_module("init.{}-{}.conv".format(num_channels, conv_dim),
                              nn.Conv2d(num_channels, conv_dim, 4, 2, 1,
                                        bias=False))
        self.layer.add_module("init.{}.relu".format(conv_dim),
                              nn.LeakyReLU(0.2, inplace=True))

        conv_size = image_size / 2
        conv_depth = conv_dim

        # extra conv layers
        for idx in range(num_extra_layers):
            self.layer.add_module(
                "extra-{}.{}-{}.conv".format(idx, conv_depth, conv_depth),
                nn.Conv2d(conv_depth, conv_depth, 3, 1, 0, bias=False))
            if use_BN:
                self.layer.add_module(
                    "extra-{}.{}.batchnorm".format(idx, conv_depth),
                    nn.BatchNorm2d(conv_depth * 2))
            self.layer.add_module(
                "extra-{}.{}.relu".format(idx, conv_depth),
                nn.LeakyReLU(0.2, inplace=True))

        # pyramid conv layer
        while conv_size > 4:
            # output (conv_depth * 2) * (conv_size / 2) * (conv_size / 2)
            self.layer.add_module(
                "pyramid.{}-{}.conv".format(conv_depth, conv_depth * 2),
                nn.Conv2d(conv_depth, conv_depth * 2, 4, 2, 1, bias=False))
            if use_BN:
                self.layer.add_module(
                    "pyramid.{}.batchnorm".format(conv_depth * 2),
                    nn.BatchNorm2d(conv_depth * 2))
            self.layer.add_module(
                "pyramid.{}.relu".format(conv_depth * 2),
                nn.LeakyReLU(0.2, inplace=True))
            conv_depth *= 2
            conv_size /= 2

        # output conv layer
        # no more sigmoid function
        # output [conv_depth x 4 x 4]
        # e.g. if image_size = 64, then output is [(conv_dim * 8) x 4 x 4]
        self.layer.add_module("final.{}-{}.conv".format(conv_depth, 1),
                              nn.Conv2d(conv_depth, 1, 4, 1, 0, bias=False))

    def forward(self, input):
        """Forward step for Discriminator model."""
        if isinstance(input.data, torch.cuda.FloatTensor) and \
                self.num_gpu > 1:
            out = nn.parallel.data_parallel(
                self.layer, input, range(self.num_gpu))
        else:
            out = self.layer(input)
        return out.view(-1, 1).squeeze(1)


class Generator(nn.Module):
    """Model for Generator."""

    def __init__(self, num_channels, z_dim, conv_dim, image_size, num_gpu,
                 num_extra_layers, use_BN):
        """Init for Generator model."""
        super(Generator, self).__init__()
        assert image_size % 16 == 0, "image size must be a multiple of 16!"

        self.num_gpu = num_gpu
        # self.layer = nn.Sequential(
        #     # 1st deconv layer, input Z, output (conv_dim*8) x 4 x 4
        #     nn.ConvTranspose2d(z_dim, conv_dim * 8, 4, 1, 0, bias=False),
        #     nn.BatchNorm2d(conv_dim * 8),
        #     nn.ReLU(True),
        #     # 2nd deconv layer, output (conv_dim*4) x 8 x 8
        #     nn.ConvTranspose2d(conv_dim * 8, conv_dim * \
        #                        4, 4, 2, 1, bias=False),
        #     nn.BatchNorm2d(conv_dim * 4),
        #     nn.ReLU(True),
        #     # 3rd deconv layer, output (conv_dim*2) x 16 x 16
        #     nn.ConvTranspose2d(conv_dim * 4, conv_dim * \
        #                        2, 4, 2, 1, bias=False),
        #     nn.BatchNorm2d(conv_dim * 2),
        #     nn.ReLU(True),
        #     # 4th deconv layer, output (conv_dim) x 32 x 32
        #     nn.ConvTranspose2d(conv_dim * 2, conv_dim, 4, 2, 1, bias=False),
        #     nn.BatchNorm2d(conv_dim),
        #     nn.ReLU(True),
        #     # output layer, output (num_channels) x 64 x 64
        #     nn.ConvTranspose2d(conv_dim, num_channels, 4, 2, 1, bias=False),
        #     nn.Tanh(),
        # )
        self.layer = nn.Sequential()

        conv_depth = conv_dim // 2
        conv_size = 4

        while conv_size != image_size:
            conv_depth = conv_depth * 2
            conv_size *= 2

        # input convt layer
        # input is Z
        # output is [conv_depth x 4 x 4]
        # e.g. if image_size = 64, then output is [(conv_dim * 8) x 4 x 4]
        self.layer.add_module(
            "init.{}-{}.convt".format(z_dim, conv_depth),
            nn.ConvTranspose2d(z_dim, conv_depth, 4, 1, 0, bias=False))
        if use_BN:
            self.layer.add_module(
                "init.{}.batchnorm".format(conv_depth),
                nn.BatchNorm2d(conv_depth))
        self.layer.add_module(
            "init.{}.relu".format(conv_depth),
            nn.ReLU(True))

        # pyramid convt layers
        conv_size = 4
        while conv_size < image_size // 2:
            # output is [(conv_depth // 2) x (conv_size * 2) x (conv_size * 2)]
            self.layer.add_module(
                "pyramid.{}-{}.convt".format(conv_depth, conv_depth // 2),
                nn.ConvTranspose2d(conv_depth, conv_depth // 2,
                                   4, 2, 1, bias=False))
            if use_BN:
                self.layer.add_module(
                    "pyramid.{}.batchnorm".format(conv_depth // 2),
                    nn.BatchNorm2d(conv_depth // 2))
            self.layer.add_module(
                "pyramid.{}.relu".format(conv_depth // 2),
                nn.ReLU(True))
            conv_depth //= 2
            conv_size *= 2

        # extra convt layers
        for idx in range(num_extra_layers):
            self.layer.add_module(
                "extra-{}.{}-{}.conv".format(idx, conv_depth, conv_depth),
                nn.Conv2d(conv_depth, conv_depth, 3, 1, 1, bias=False))
            if use_BN:
                self.layer.add_module(
                    "extra-{}.{}.batchnorm".format(idx, conv_depth),
                    nn.BatchNorm2d(conv_depth))
            self.layer.add_module(
                "extra-{}.{}.relu".format(idx, conv_depth),
                nn.ReLU(True))

        # output convt layer
        # output is [num_channels x conv_dim x conv_dim]
        self.layer.add_module(
            "final.{}-{}.convt".format(conv_depth, num_channels),
            nn.ConvTranspose2d(conv_depth, num_channels, 4, 2, 1, bias=False))
        self.layer.add_module(
            "final.{}.tanh".format(num_channels),
            nn.Tanh())

    def forward(self, input):
        """Forward step for Generator model."""
        if isinstance(input.data, torch.cuda.FloatTensor) and \
                self.num_gpu > 1:
            out = nn.parallel.data_parallel(
                self.layer, input, range(self.num_gpu))
        else:
            out = self.layer(input)
        # flatten output
        return out


def get_models():
    """Get models with cuda and inited weights."""
    D = Discriminator(num_channels=num_channels,
                      conv_dim=d_conv_dim,
                      image_size=image_size,
                      num_gpu=num_gpu,
                      num_extra_layers=num_extra_layers,
                      use_BN=use_BN)
    G = Generator(num_channels=num_channels,
                  z_dim=z_dim,
                  conv_dim=g_conv_dim,
                  image_size=image_size,
                  num_gpu=num_gpu,
                  num_extra_layers=num_extra_layers,
                  use_BN=use_BN)

    # init weights of models
    D.apply(init_weights)
    G.apply(init_weights)

    # restore model weights
    if d_model_restore is not None and os.path.exists(d_model_restore):
        D.load_state_dict(torch.load(d_model_restore))
    if g_model_restore is not None and os.path.exists(g_model_restore):
        G.load_state_dict(torch.load(g_model_restore))

    # check if cuda is available
    if torch.cuda.is_available():
        cudnn.benchmark = True
        D.cuda()
        G.cuda()

    return D, G