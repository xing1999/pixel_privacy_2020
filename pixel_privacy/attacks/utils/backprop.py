from torchvision import models, transforms
import torch
from torch import nn
import torchvision.transforms.functional as Ftransform


import warnings
from PIL import Image


from flashtorch.utils import format_for_plotting, standardize_and_clip
from matplotlib import pyplot as plt
from torch.nn import functional as F

import os
import json

from .load_data import load_img

## Re-implement Backprop class for our precious Model class
class Backprop:
    """Provides an interface to perform backpropagation.

    This class provids a way to calculate the gradients of a target class
    output w.r.t. an input image, by performing a single backprobagation.

    The gradients obtained can be used to visualise an image-specific class
    saliency map, which can gives some intuition on regions within the input
    image that contribute the most (and least) to the corresponding output.

    More details on saliency maps: `Deep Inside Convolutional Networks:
    Visualising Image Classification Models and Saliency Maps
    <https://arxiv.org/pdf/1312.6034.pdf>`_.

    Args:
        model: A neural network model from `torchvision.models
            <https://pytorch.org/docs/stable/torchvision/models.html>`

    """

    def __init__(self, model):
        self.model = model
        self.model.eval()
        self.gradients = None
        self.handles = []

        
    def calculate_gradients(self,
                            input_,
                            target_class=None,
                            take_max=False,
                            guided=False,
                            use_gpu=True):

        """Calculates gradients of the target_class output w.r.t. an input_.

        The gradients is calculated for each colour channel. Then, the maximum
        gradients across colour channels is returned.

        Args:
            input_ (torch.Tensor): With shape :math:`(N, C, H, W)`.
            target_class (int, optional, default=None)
            take_max (bool, optional, default=False): If True, take the maximum
                gradients across colour channels for each pixel.
            guided (bool, optional, default=Fakse): If True, perform guided
                backpropagation. See `Striving for Simplicity: The All
                Convolutional Net <https://arxiv.org/pdf/1412.6806.pdf>`_.
            use_gpu (bool, optional, default=False): Use GPU if set to True and
                `torch.cuda.is_available()`.

        Returns:
            gradients (torch.Tensor): With shape :math:`(C, H, W)`.
            target_class

        """

        if 'inception' in self.model.__class__.__name__.lower():
            if input_.size()[1:] != (3, 299, 299):
                raise ValueError('Image must be 299x299 for Inception models.')

        if guided:
            self.relu_outputs = []
            self._register_relu_hooks()

        if torch.cuda.is_available() and use_gpu:
            self.model = self.model.to('cuda')
            input_ = input_.to('cuda')
        input_.requires_grad_(True)
        
        self.model.zero_grad()

        self.gradients = torch.zeros(input_.shape)

        # Get a raw prediction value (logit) from the last linear layer

        output = self.model(input_)

        # Don't set the gradient target if the model is a binary classifier
        # i.e. has one class prediction

        if len(output.shape) == 1:
            target = None
        else:
            _, top_class = output.topk(1, dim=1)

            # Create a 2D tensor with shape (1, num_classes) and
            # set all element to zero

            target = torch.FloatTensor(1, output.shape[-1]).zero_()

            if torch.cuda.is_available() and use_gpu:
                target = target.to('cuda')

            if (target_class is not None) and (top_class != target_class):
                warnings.warn(UserWarning(
                    f'The predicted class index {top_class.item()} does not' +
                    f'equal the target class index {target_class}. Calculating' +
                    'the gradient w.r.t. the predicted class.'
                ))

            # Set the element at top class index to be 1

            target[0][top_class] = 1

        # Calculate gradients of the target class output w.r.t. input_

        output.backward(gradient=target)

        # Detach the gradients from the graph and move to cpu

        gradients = input_.grad.data.cpu()

        if take_max:
            # Take the maximum across colour channels

            gradients = gradients.max(dim=0, keepdim=True)[0]

        return gradients, top_class

    def _register_relu_hooks(self):
        def _record_output(module, input_, output):
            self.relu_outputs.append(output)

        def _clip_gradients(module, grad_in, grad_out):
            relu_output = self.relu_outputs.pop()
            clippled_grad_out = grad_out[0].clamp(0.0)

            return (clippled_grad_out.mul(relu_output),)

        for _, module in self.model.named_modules():
            if isinstance(module, nn.ReLU):
                self.handles.append(module.register_forward_hook(_record_output))
                self.handles.append(module.register_backward_hook(_clip_gradients))
  
    def __del__(self):
      for handle in self.handles:
        handle.remove()



def get_input_gradient(model, fname,guided=True, take_max=False, use_gpu=True):
  '''Warper for getting image gradient + cool visualize for it
  Input:
    model: (__main__.Model) Model 
    fname: (str) Image file path
  
  Output:
    gradient for fname 
  
  
  '''
  ## Load image file
  img = load_img(fname)
  backprop = Backprop(model)
  output, target_class = backprop.calculate_gradients(img, None, take_max, guided, use_gpu)
  
  # Reshaping img gradient - Remove batch + move channel to last dim
  x = output
  output = format_for_plotting(output) 
  clip_grad = standardize_and_clip(output) #Clip gradient of image from 0 -> 1
  
  print(f'Model predicted {target_class}')
  
  fig = plt.figure()
  ax = fig.add_subplot(1, 3, 1)
  ax.set_axis_off()
  ax.imshow(clip_grad)
  ax.set_title('Gradient')
  
  ax = fig.add_subplot(1, 3, 2)
  ax.set_axis_off()
  ax.imshow(format_for_plotting(img))
  ax.set_title('Original image')

  
  ax = fig.add_subplot(1, 3, 3)
  ax.set_axis_off()
  ax.imshow(format_for_plotting(img))
  ax.imshow(clip_grad, alpha=0.3)
  ax.set_title('Blend grad and\n original image')

  
  
  fig.show()
  return output, x

### Test - Please update your file
