from __future__ import (absolute_import, division, print_function,
                        unicode_literals, with_statement)

import argparse
import copy
import os.path as osp
import random
import json
import sys
import time
import traceback
from datetime import datetime as dt

import cleanlab
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torchvision
from cleanlab.classification import LearningWithNoisyLabels
from cleanlab.latent_algebra import compute_inv_noise_matrix
# from cleanlab.models.mnist_pytorch import CNN
from cleanlab.noise_generation import generate_noisy_labels
from cleanlab.util import value_counts
from PIL import Image
from sklearn.base import BaseEstimator
# from sklearn import datasets
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import ParameterGrid, train_test_split
from torch.autograd import Variable
from torch.utils.data import DataLoader
from torch.utils.data.sampler import SubsetRandomSampler
from torchvision import datasets, transforms

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42


def call_bn(bn, x):
    return bn(x)


class CIFAR10_CNN(nn.Module):
    """A CNN architecture shown to be a good baseline for a CIFAR-10 benchmark.
    Parameters
    ----------
    input_channel : int
    n_outputs : int
    dropout_rate : float
    top_bn : bool

    Methods
    -------
    forward
      forward pass in PyTorch"""

    def __init__(self, input_channel=3, n_outputs=10, dropout_rate=0.25,
                 top_bn=False):
        self.dropout_rate = dropout_rate
        self.top_bn = top_bn
        super(CIFAR10_CNN, self).__init__()
        self.c1 = nn.Conv2d(
            input_channel, 128, kernel_size=3, stride=1, padding=1)
        self.c2 = nn.Conv2d(128, 128, kernel_size=3, stride=1, padding=1)
        self.c3 = nn.Conv2d(128, 128, kernel_size=3, stride=1, padding=1)
        self.c4 = nn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1)
        self.c5 = nn.Conv2d(256, 256, kernel_size=3, stride=1, padding=1)
        self.c6 = nn.Conv2d(256, 256, kernel_size=3, stride=1, padding=1)
        self.c7 = nn.Conv2d(256, 512, kernel_size=3, stride=1, padding=0)
        self.c8 = nn.Conv2d(512, 256, kernel_size=3, stride=1, padding=0)
        self.c9 = nn.Conv2d(256, 128, kernel_size=3, stride=1, padding=0)
        self.l_c1 = nn.Linear(128, n_outputs)
        self.bn1 = nn.BatchNorm2d(128)
        self.bn2 = nn.BatchNorm2d(128)
        self.bn3 = nn.BatchNorm2d(128)
        self.bn4 = nn.BatchNorm2d(256)
        self.bn5 = nn.BatchNorm2d(256)
        self.bn6 = nn.BatchNorm2d(256)
        self.bn7 = nn.BatchNorm2d(512)
        self.bn8 = nn.BatchNorm2d(256)
        self.bn9 = nn.BatchNorm2d(128)

    def forward(self, x, ):
        h = x
        h = self.c1(h)
        h = F.leaky_relu(call_bn(self.bn1, h), negative_slope=0.01)
        h = self.c2(h)
        h = F.leaky_relu(call_bn(self.bn2, h), negative_slope=0.01)
        h = self.c3(h)
        h = F.leaky_relu(call_bn(self.bn3, h), negative_slope=0.01)
        h = F.max_pool2d(h, kernel_size=2, stride=2)
        h = F.dropout2d(h, p=self.dropout_rate)

        h = self.c4(h)
        h = F.leaky_relu(call_bn(self.bn4, h), negative_slope=0.01)
        h = self.c5(h)
        h = F.leaky_relu(call_bn(self.bn5, h), negative_slope=0.01)
        h = self.c6(h)
        h = F.leaky_relu(call_bn(self.bn6, h), negative_slope=0.01)
        h = F.max_pool2d(h, kernel_size=2, stride=2)
        h = F.dropout2d(h, p=self.dropout_rate)

        h = self.c7(h)
        h = F.leaky_relu(call_bn(self.bn7, h), negative_slope=0.01)
        h = self.c8(h)
        h = F.leaky_relu(call_bn(self.bn8, h), negative_slope=0.01)
        h = self.c9(h)
        h = F.leaky_relu(call_bn(self.bn9, h), negative_slope=0.01)
        h = F.avg_pool2d(h, kernel_size=h.data.shape[2])

        h = h.view(h.size(0), h.size(1))
        logit = self.l_c1(h)
        if self.top_bn:
            logit = call_bn(self.bn_c1, logit)
        logit = F.log_softmax(logit, dim=1)
        return logit


class MNIST_CNN(nn.Module):
    """Basic Pytorch CNN for MNIST-like data."""

    def __init__(self):
        super(MNIST_CNN, self).__init__()
        self.conv1 = nn.Conv2d(1, 10, kernel_size=5)
        self.conv2 = nn.Conv2d(10, 20, kernel_size=5)
        self.conv2_drop = nn.Dropout2d()
        self.fc1 = nn.Linear(320, 50)
        self.fc2 = nn.Linear(50, 10)

    def forward(self, x, T=1.0):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d(self.conv2_drop(self.conv2(x)), 2))
        x = x.view(-1, 320)
        x = F.relu(self.fc1(x))
        x = F.dropout(x, training=self.training)
        x = self.fc2(x)
        x = F.log_softmax(x, dim=1)
        return x


def imshow(inp, img_labels=None, img_pred=None, img_fns=None, figsize=(10, 10), normalize=False, red_boxes=True,
           savefig=False):
    """Imshow for Tensor."""
    height, width = inp.shape[1:]
    ROW_NUMS = 8
    xbins = ROW_NUMS
    ybins = int(np.ceil(len(img_labels) / xbins))
    xbin_width = width // xbins
    ybin_height = height // ybins

    inp = inp.numpy().transpose((1, 2, 0))
    if normalize:
        mean = np.array([0.485, 0.456, 0.406])
        std = np.array([0.229, 0.224, 0.225])
        inp = std * inp + mean
        inp = np.clip(inp, 0, 1)

    ax = plt.figure(figsize=figsize).gca()
    ax.imshow(inp)
    pad_size = (ROW_NUMS - len(img_pred) % ROW_NUMS) % ROW_NUMS
    img_labels = img_labels + [''] * pad_size  # padding
    img_pred = img_pred + [''] * pad_size  # padding
    img_fns = img_fns + [''] * pad_size  # padding
    #     grid = np.asarray(img_labels).reshape((ybins, xbins))

    num_red_boxes = 0
    for (j, i), idx in np.ndenumerate(np.arange(ybins * xbins).reshape((ybins, xbins))):
        prediction = img_pred[idx]
        label = img_labels[idx]
        img_fn = img_fns[idx]
        # image_index = int(img_fn[13:])

        plt.hlines([j * ybin_height - .5], xmin=i * xbin_width, xmax=i * xbin_width + xbin_width, color='lightgray',
                   linewidth=2)

        fontsize = max(min(1.4 * figsize[0], .9 * figsize[0] - .7 * len(prediction)), 12) if prediction != '' else 1
        tt = ax.text(i * xbin_width + xbin_width / 2, j * ybin_height + ybin_height / 20, prediction, ha='center',
                     va='center', fontsize=fontsize)
        tt.set_bbox(dict(facecolor='lime', alpha=0.8, edgecolor=None))

        fontsize = min(.5 * figsize[0], 1.25 * figsize[0] - len(img_fn)) if img_fn != '' else 1
        tt = ax.text(i * xbin_width + xbin_width / 2.8, j * ybin_height + ybin_height / 7, img_fn, ha='center',
                     va='center', fontsize=fontsize)
        tt.set_bbox(dict(facecolor='lightgray', alpha=0.8, edgecolor=None))

        fontsize = max(min(1.4 * figsize[0], .9 * figsize[0] - .7 * len(label)), 12) if label != '' else 1
        t = ax.text(i * xbin_width + xbin_width / 2, j * ybin_height + ybin_height / 10 * 9, label, ha='center',
                    va='center', fontsize=fontsize)
        t.set_bbox(dict(facecolor='cyan', alpha=0.8, edgecolor=None))

        if not red_boxes:
            plt.vlines([i * xbin_width + 0.5, (i + 1) * xbin_width - 1.5], ymin=j * ybin_height + 0.5,
                       ymax=j * ybin_height + ybin_height - 0.5, color='gray', linewidth=5)

        else:
        # if red_boxes and image_index in red_box_idxs:
            # Draw red bounding box
            num_red_boxes += 1
            plt.hlines([j * ybin_height + 0.5, (j + 1) * ybin_height - 1.5], xmin=i * xbin_width - 0.3,
                       xmax=i * xbin_width + xbin_width - 0.65, color='red', linewidth=15)
            plt.vlines([i * xbin_width + 0.5, (i + 1) * xbin_width - 1.5], ymin=j * ybin_height + 0.5,
                       ymax=j * ybin_height + ybin_height - 0.5, color='red', linewidth=15)

    if red_boxes:
        print('Number of red boxes:', num_red_boxes)
    plt.axis('off')
    if savefig:
        plt.savefig('figs/mnist_test_label_errors' + str(len(img_labels)) + '.pdf', pad_inches=0.0, bbox_inches='tight')
    plt.pause(0.001)  # pause a bit so that plots are updated


def get_pert(PERT_NUM, y_ori, y_pert):
    '''
    PERT_NUM: int -- ????????????????????????
    y_ori: np.array -- ?????????????????????
    y_pert: np.array -- ????????????????????????
    '''
    pert_list = []
    for i in range(PERT_NUM):
        rand_num = random.randint(0, 9)
        data_index = random.randint(0, len(y_pert) - 1)
        while y_ori[data_index] != y_pert[data_index]:  # ??????????????????????????????
            data_index = random.randint(0, len(y_pert) - 1)
        pert_list.append(data_index)
        while rand_num == y_pert[data_index]:
            rand_num = random.randint(0, 9)
        y_pert[data_index] = rand_num
    # red_box_idxs=random.sample(pert_list,8)
    return y_pert, pert_list


class CNN(BaseEstimator):  # Inherits sklearn classifier
    """Wraps a PyTorch CNN for the Pytorch dataset within an sklearn template
    Defines ``.fit()``, ``.predict()``, and ``.predict_proba()`` functions. This
    template enables the PyTorch CNN to flexibly be used within the sklearn
    architecture -- meaning it can be passed into functions like
    cross_val_predict as if it were an sklearn model. The cleanlab library
    requires that all models adhere to this basic sklearn template and thus,
    this class allows a PyTorch CNN to be used in for learning with noisy
    labels among other things.
    Parameters
    ----------
    batch_size: int
    epochs: int
    log_interval: int
    lr: float
    momentum: float
    no_cuda: bool
    seed: int
    test_batch_size: int, default=None
    dataset: {'MNIST', 'CIFAR10'}
    testloader: Dataloader
    train_loader: Dataloader

    Attributes
    ----------
    batch_size: int
    epochs: int
    log_interval: int
    lr: float
    momentum: float
    no_cuda: bool
    seed: int
    test_batch_size: int, default=None
    dataset: {'MNIST', 'CIFAR10'}
    Methods
    -------
    fit
      fits the model to data.
    predict
      get the fitted model's prediction on test data
    predict_proba
      get the fitted model's probability distribution over clases for test data
    """

    def __init__(
            self,
            test_loader,
            train_loader,
            test_size=10000,
            batch_size=64,
            epochs=6,
            log_interval=50,  # Set to None to not print
            lr=0.01,
            momentum=0.5,
            no_cuda=False,
            seed=1,
            test_batch_size=None,
            dataset='MNIST'
    ):
        self.test_loader = test_loader
        self.train_loader = train_loader
        self.test_size = test_size
        self.batch_size = batch_size
        self.epochs = epochs
        self.log_interval = log_interval
        self.lr = lr
        self.momentum = momentum
        self.no_cuda = no_cuda
        self.seed = seed
        self.cuda = not self.no_cuda and torch.cuda.is_available()
        torch.manual_seed(self.seed)
        if self.cuda:  # pragma: no cover
            torch.cuda.manual_seed(self.seed)

        # Instantiate PyTorch model

        if dataset == 'MNIST':
            self.model = MNIST_CNN()
        elif dataset == 'CIFAR10':
            self.model = CIFAR10_CNN()
        else:
            raise ValueError("dataset must be 'MNIST' or 'CIFAR10'.")

        if test_batch_size is None:
            self.test_batch_size = self.test_size

        if self.cuda:  # pragma: no cover
            self.model.cuda()

        self.loader_kwargs = {'num_workers': 1,
                              'pin_memory': True} if self.cuda else {}

    def fit(self, train_idx, train_labels=None, sample_weight=None):
        """This function adheres to sklearn's "fit(X, y)" format for
        compatibility with scikit-learn. ** All inputs should be numpy
        arrays, not pyTorch Tensors train_idx is not X, but instead a list of
        indices for X (and y if train_labels is None). This function is a
        member of the cnn class which will handle creation of X, y from the
        train_idx via the train_loader. """
        #         if self.loader is not None:
        #             loader = self.loader
        if train_labels is not None and len(train_idx) != len(train_labels):
            raise ValueError(
                "Check that train_idx and train_labels are the same length.")

        if sample_weight is not None:  # pragma: no cover
            if len(sample_weight) != len(train_labels):
                raise ValueError("Check that train_labels and sample_weight "
                                 "are the same length.")
            class_weight = sample_weight[
                np.unique(train_labels, return_index=True)[1]]
            class_weight = torch.from_numpy(class_weight).float()
            if self.cuda:
                class_weight = class_weight.cuda()
        else:
            class_weight = None

        train_loader = self.train_loader

        optimizer = optim.SGD(self.model.parameters(), lr=self.lr,
                              momentum=self.momentum)

        # Train for self.epochs epochs
        for epoch in range(1, self.epochs + 1):

            # Enable dropout and batch norm layers
            self.model.train()
            for batch_idx, (data, target) in enumerate(train_loader):
                if self.cuda:  # pragma: no cover
                    data, target = data.cuda(), target.cuda()
                data, target = Variable(data), Variable(target).long()
                optimizer.zero_grad()
                output = self.model(data)
                loss = F.nll_loss(output, target, class_weight)
                loss.backward()
                optimizer.step()
                if self.log_interval is not None and \
                        batch_idx % self.log_interval == 0:
                    print(
                        'TrainEpoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                            epoch, batch_idx * len(data), len(train_idx),
                                   100. * batch_idx / len(train_loader),
                            loss.item()),
                    )

    def predict(self, idx=None):
        """Get predicted labels from trained model."""
        # get the index of the max probability
        probs = self.predict_proba(idx)
        return probs.argmax(axis=1)

    def predict_proba(self, idx=None):
        loader = self.test_loader
        dataset = copy.deepcopy(loader.dataset)
        if idx is not None:
            if len(idx) != self.test_size:
                dataset.data = np.array(dataset.data)[idx]
                #                 if type(dataset.targets)==list:
                #                     dataset.targets=np.array(dataset.targets)
                dataset.targets = np.array(dataset.targets)[idx]

        loader = torch.utils.data.DataLoader(
            dataset=dataset,
            batch_size=self.test_batch_size,
            **self.loader_kwargs
        )

        # sets model.train(False) inactivating dropout and batch-norm layers
        self.model.eval()

        # Run forward pass on model to compute outputs
        outputs = []
        for data, _ in loader:
            if self.cuda:  # pragma: no cover
                data = data.cuda()
            with torch.no_grad():
                data = Variable(data)
                output = self.model(data)
            outputs.append(output)

        # Outputs are log_softmax (log probabilities)
        outputs = torch.cat(outputs, dim=0)
        # Convert to probabilities and return the numpy array of shape N x K
        out = outputs.cpu().numpy() if self.cuda else outputs.numpy()
        pred = np.exp(out)
        return pred


def run_cleanlab(train_loader, test_loader, root, dataset='MNIST', batch_size=128, PERT_NUM=16, MAX_IMAGES=32,
                 log_func=None):
    '''
    Parameters
    ------
    dataset: {'MNIST', 'CIFAR10'}
    train_loader: torch.utils.data.DataLoader
    test_loader: torch.utils.data.DataLoader
    PERT_NUM: int
        amount of added noisy labels
        -- ????????????????????????
    MAX_IMAGES: int
        max images shown
    savefig: bool
    '''

    TEST_SIZE = batch_size
    TRAIN_SIZE = 60000
    X_train = np.arange(TRAIN_SIZE)
    X_test = np.arange(TEST_SIZE)
    s, y = iter(test_loader).next()
    X_test_data, y_test = next(iter(test_loader))
    y_test = y_test.numpy()
    X_test_data = X_test_data.numpy()

    y_ori = y_test.copy()
    print("get_pert")
    y_test, red_box_idxs = get_pert(PERT_NUM, y_ori, y_test)  # get noisy label for testing

    np.random.seed(43)
    savefig = False
    prune_method = 'prune_by_noise_rate'
    t_begin = time.time()
    # Pre-train
    print("cnn.fit")
    cnn = CNN(epochs=10, log_interval=1000, train_loader=train_loader, test_loader=test_loader,
              dataset=dataset)  # pre-train
    cnn.fit(X_test, y_test)  # pre-train (overfit, not out-of-sample) to entire dataset.

    # Out-of-sample cross-validated holdout predicted probabilities
    np.random.seed(4)
    cnn.epochs = 1  # Single epoch for cross-validation (already pre-trained)

    jc, psx = cleanlab.latent_estimation.estimate_confident_joint_and_cv_pred_proba(X_test, y_test, cnn, cv_n_folds=5)
    est_py, est_nm, est_inv = cleanlab.latent_estimation.estimate_latent(jc, y_test)
    # algorithmic identification of label errors
    noise_idx = cleanlab.pruning.get_noise_indices(y_test, psx, est_inv, prune_method=prune_method)
    print('Number of estimated errors in test set:', sum(noise_idx))

    noise_idx = np.asarray(
        [i in red_box_idxs for i in range(len(y_test))])  # hand-picked digits from rankpruning alg's results
    pred = np.argmax(psx, axis=1)
    t_end = time.time()
    fix_rate = sum((pred == y_ori) & (y_test != y_ori)) / PERT_NUM
    print('fix rate:', fix_rate)
    all_time = (t_end - t_begin) * 1000
    print('time usage:{} ms'.format(all_time))

    ordered_noise_idx = np.argsort(np.asarray([psx[i][j] for i, j in enumerate(y_test)])[noise_idx])
    prob_given = np.asarray([psx[i][j] for i, j in enumerate(y_test)])[noise_idx][ordered_noise_idx][:MAX_IMAGES]
    prob_pred = np.asarray([psx[i][j] for i, j in enumerate(pred)])[noise_idx][ordered_noise_idx][:MAX_IMAGES]
    img_idx = np.arange(len(noise_idx))[noise_idx][ordered_noise_idx][:MAX_IMAGES]
    label4viz = y_test[noise_idx][ordered_noise_idx][:MAX_IMAGES]
    pred4viz = pred[noise_idx][ordered_noise_idx][:MAX_IMAGES]

    if dataset == 'MNIST':
        graphic = torchvision.utils.make_grid(
            torch.from_numpy(np.concatenate([X_test_data[img_idx][:, None]] * 3, axis=1).squeeze()))
    elif dataset == 'CIFAR10':
        graphic = torchvision.utils.make_grid(torch.from_numpy(np.array([X_test_data[img_idx][:, None]]).squeeze()))
    img_labels = ["given: " + str(label4viz[w]) + " | conf: " + str(np.round(prob_given[w], 3)) for w in
                  range(len(label4viz))]
    img_pred = ["convnet guess: " + str(pred4viz[w]) + " | conf: " + str(np.round(prob_pred[w], 3)) for w in
                range(len(pred4viz))]
    img_fns = ["train img #: " + str(item) for item in img_idx]
    # Display image
    imshow(
        graphic,
        img_labels=img_labels,
        img_pred=img_pred,
        img_fns=img_fns,
        figsize=(40, MAX_IMAGES / 1.1),
        red_boxes=False,
        #     savefig = savefig,
    )
    # plt.savefig('/data2/gxq/SecPlat/SecAladdin/static/img/{}_example.png'.format(filename))
    # plt.show()

    wr_matrix = np.zeros((10, 10))
    mask = np.eye(10)
    for i in range(len(y_test)):
        wr_matrix[pred[i], y_ori[i]] += 1

    # clean_heatmap=sns.heatmap(wr_matrix,annot=True,mask=mask,annot_kws={"fontsize":8})
    # clean_heatmap.get_figure().savefig('/data2/gxq/SecPlat/SecAladdin/static/img/{}_heatmap.png'.format(filename))

    # json_path = osp.join(root, "keti2/keti2.json")
    json_path = osp.join(root, "keti2.json")
    with open(json_path, 'r') as f:
        res_dict = json.load(f)
    res_dict["abnormal_data"]["fix_rate"] = fix_rate
    with open(json_path, 'w') as f:
        json.dump(res_dict, f)
    return fix_rate


def run(train_loader, test_loader, params, log_func=None):
    batch_size = test_loader.batch_size
    dataset = params["dataset"]["name"].upper()
    root = osp.join(params["out_path"], "keti2")
    # print("run_cleanlab")
    run_cleanlab(train_loader, test_loader, root=root, dataset=dataset, batch_size=batch_size, PERT_NUM=16,
                 MAX_IMAGES=32, log_func=log_func)


"""??????????????????"""

def data_detection():
    train_data = torchvision.datasets.CIFAR10("./data",train=True,transform=torchvision.transforms.ToTensor(),download=True)
    train_loader = DataLoader(dataset=train_data,batch_size=64,shuffle=True,num_workers=0,drop_last=True)
    test_data = torchvision.datasets.CIFAR10("./data", train=False, transform=torchvision.transforms.ToTensor(),
                                              download=True)
    test_loader = DataLoader(dataset=test_data, batch_size=64, shuffle=True, num_workers=0, drop_last=True)
    params = {
        "dataset":{
            "name":"CIFAR10"
        },
        "out_path":"./"
    }
    # print("run")
    run(train_loader,test_loader,params)

if __name__ == "__main__":
    data_detection()
