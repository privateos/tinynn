# Author: borgwang <borgwang@126.com>
# Date: 2018-05-05
#
# Filename: BaseOptimizer.py
# Description:
#   Implement multiple optimization algorithms and learning rate scheuler.


from typing import List

import numpy as np
from core.nn import NeuralNet
from core.tensor import Tensor


# ----------
# Optimizer
# ----------

class BaseOptimizer(object):

    def __init__(self, lr, weight_decay):
        self.lr = lr
        self.weight_decay = weight_decay

    def step(self, net):
        # flatten all gradients
        flatten_grads = np.concatenate(
            [np.ravel(grad) for param, grad in net.get_params_and_grads()])
        flatten_step = self._compute_step(flatten_grads)

        p = 0
        step = []
        for param, grad in net.get_params_and_grads():
            block = np.prod(param.shape)
            _step = flatten_step[p: p+block].reshape(param.shape) - self.weight_decay * param
            step.append(_step)
            param += _step
            p += block
        return step

    def _compute_step(self, grad):
        raise NotImplementedError


class SGD(BaseOptimizer):

    def __init__(self, lr, weight_decay=0.0):
        super().__init__(lr, weight_decay)

    def _compute_step(self, grad):
        return - self.lr * grad


class Adam(BaseOptimizer):

    def __init__(self,
                 lr=0.001,
                 beta1=0.9,
                 beta2=0.999,
                 eps=1e-8,
                 weight_decay=0.0):
        super().__init__(lr, weight_decay)
        self._b1 = beta1
        self._b2 = beta2
        self._eps = eps

        self._t= 0
        self._m= 0
        self._v= 0

    def _compute_step(self, grad):
        self._t += 1

        lr_t = self.lr * np.sqrt(1 - np.power(self._b2, self._t)) / \
            (1 - np.power(self._b1, self._t))

        self._m = self._b1 * self._m + (1 - self._b1) * grad
        self._v = self._b2 * self._v + (1 - self._b2) * np.square(grad)

        step = -lr_t * self._m / (np.sqrt(self._v) + self._eps)

        return step


class RMSProp(BaseOptimizer):
    '''
    RMSProp maintain a moving (discouted) average of the square of gradients.
    Then divide gradients by the root of this average.

    mean_square = decay * mean_square{t-1} + (1-decay) * grad_t**2
    mom = momentum * mom{t-1} + lr * grad_t / sqrt(mean_square + epsilon)
    '''
    def __init__(self,
                 lr=0.01,
                 decay=0.99,
                 momentum=0.0,
                 eps=1e-8,
                 weight_decay=0.0):
        super().__init__(lr, weight_decay)
        self._decay = decay
        self._momentum = momentum
        self._eps = eps

        self._ms: Tensor = 0
        self._mom: Tensor = 0

    def _compute_step(self, grad):
        self._ms = self._decay * self._ms + (1 - self._decay) * np.square(grad)
        self._mom = self._momentum * self._mom + \
            self.lr * grad / np.sqrt(self._ms + self._eps)

        step = -self._mom
        return step


class Momentum(BaseOptimizer):
    '''
     accumulation = momentum * accumulation + gradient
     variable -= learning_rate * accumulation
    '''
    def __init__(self, lr, momentum=0.9, weight_decay=0.0):
        super().__init__(lr, weight_decay)
        self._momentum = momentum
        self._acc: Tensor = 0

    def _compute_step(self, grad):
        self._acc = self._momentum * self._acc + grad
        step: Tensor = -self.lr * self._acc
        return step


# ----------
# Learning Rate Scheduler
# ----------

class BaseScheduler(object):
    '''
    BaseScheduler model receive a optimizer and Adjust the lr by calling
    step() method during training.
    '''
    def __init__(self):
        self._optim = None
        self._initial_lr = self.get_current_lr()

        self._t: int = 0

    def step(self):
        self._t += 1
        self._optim.lr = self._compute_lr()
        return self.get_current_lr()

    def _compute_lr(self):
        raise NotImplementedError

    def get_current_lr(self):
        return self._optim.lr


class StepLR(BaseScheduler):
    '''
    LR decayed by gamma every 'step_size' epoches.
    '''
    def __init__(self,
                 optimizer,
                 step_size,
                 gamma=0.1):
        super().__init__(optimizer)
        assert step_size >= 1, 'step_size must greater than 0 (%d was set)' % step_size
        self._step_size = step_size
        self._gamma = gamma

    def _compute_lr(self):
        decay = self._gamma if self._t % self._step_size == 0 else 1.0
        return decay * self.get_current_lr()


class MultiStepLR(BaseScheduler):
    '''
    LR decayed by gamma when the number of epoch reaches one of the milestones.
    Argument 'milestones' must be a int list and be increasing.
    '''
    def __init__(self,
                 optimizer,
                 milestones,
                 gamma=0.1):
        super().__init__(optimizer)
        milestones = [int(m) for m in milestones]
        assert all(x < y for x, y in zip(milestones[:-1], milestones[1:])) and \
            all(isinstance(x, int) for x in milestones), \
            'milestones must be a list of int and be increasing!'

        self._milestones = milestones
        self._gamma = gamma

    def _compute_lr(self):
        decay = self._gamma if self._t in self._milestones else 1.0
        return decay * self.get_current_lr()


class ExponentialLR(BaseScheduler):
    '''
    ExponentialLR is computed by:

    lr_decayed = lr * decay_rate ^ (current_steps / decay_steps)
    '''
    def __init__(self,
                 optimizer,
                 decay_steps,
                 decay_rate=(1 / np.e)):
        super().__init__(optimizer)
        self._decay_steps = decay_steps
        self._decay_rate = decay_rate

    def _compute_lr(self):
        if self._t <= self._decay_steps:
            return self._initial_lr * \
                self._decay_rate ** (self._t  / self._decay_steps)
        else:
            return self.get_current_lr()


class LinearLR(BaseScheduler):
    '''
    Linear decay learning rate when the number of the epoche is in
    [start_step, start_step + decay_steps]
    '''
    def __init__(self,
                 optimizer,
                 decay_steps,
                 final_lr=1e-6,
                 start_step=0):
        super().__init__(optimizer)
        assert final_lr < self._initial_lr, \
            'The final lr should be no greater than the initial lr.'
        assert decay_steps > 0

        self._lr_delta = (final_lr - self._initial_lr) / decay_steps

        self._final_lr = final_lr
        self._decay_steps = decay_steps
        self._start_step = start_step

    def _compute_lr(self):
        if self._t > self._start_step:
            if self._t <= self._start_step + self._decay_steps:
                return self.get_current_lr() + self._lr_delta
        return self.get_current_lr()
