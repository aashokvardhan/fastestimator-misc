# Copyright 2019 The FastEstimator Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import tempfile

import tensorflow as tf

import fastestimator as fe
from fastestimator.architecture.tensorflow import LeNet
from fastestimator.dataset.data import mnist
from fastestimator.op.numpyop.univariate import ExpandDims, Minmax
from fastestimator.op.tensorop.loss import CrossEntropy
from fastestimator.op.tensorop.model import ModelOp, UpdateOp
from fastestimator.op.tensorop.gradient import GradientOp, Watch
from fastestimator.schedule import cosine_decay
from fastestimator.trace.adapt import LRScheduler
from fastestimator.trace.io import BestModelSaver, TensorBoard
from fastestimator.trace.metric import Accuracy
from fastestimator.trace import Trace
from fastestimator.util import Data


class Inspector(Trace):
    def __init__(self):
        super().__init__(inputs='grads')

    def on_batch_end(self, data: Data) -> None:
        grads = tf.reduce_max(tf.abs(data.get('grads')))
        print(grads)


def get_estimator(epochs=2,
                  batch_size=32,
                  max_train_steps_per_epoch=None,
                  max_eval_steps_per_epoch=None,
                  save_dir=tempfile.mkdtemp()):
    # step 1
    train_data, eval_data = mnist.load_data()
    test_data = eval_data.split(0.5)
    pipeline = fe.Pipeline(train_data=train_data,
                           eval_data=eval_data,
                           test_data=test_data,
                           batch_size=batch_size,
                           ops=[ExpandDims(inputs="x", outputs="x"), Minmax(inputs="x", outputs="x")],
                           num_process=0)

    # step 2
    model = fe.build(model_fn=LeNet, optimizer_fn="adam")
    print([f"{idx}: {x.name}" for idx, x in enumerate(model.submodules)])
    network = fe.Network(ops=[
        Watch(inputs="x"),
        ModelOp(model=model, inputs="x", outputs=["y_pred", "embedding"], intermediate_layers='dense'),
        CrossEntropy(inputs=("y_pred", "y"), outputs="ce"),
        GradientOp(finals="embedding", inputs="x", outputs="grads"),
        UpdateOp(model=model, loss_name="ce")
    ])
    # step 3
    traces = [
        Accuracy(true_key="y", pred_key="y_pred"),
        Inspector(),
        BestModelSaver(model=model, save_dir=save_dir, metric="accuracy", save_best_mode="max"),
        LRScheduler(model=model, lr_fn=lambda step: cosine_decay(step, cycle_length=3750, init_lr=1e-3)),
        TensorBoard(log_dir="tf_logs", write_embeddings="embedding", embedding_labels="y")
    ]
    estimator = fe.Estimator(pipeline=pipeline,
                             network=network,
                             epochs=epochs,
                             traces=traces,
                             max_train_steps_per_epoch=max_train_steps_per_epoch,
                             max_eval_steps_per_epoch=max_eval_steps_per_epoch)
    return estimator


if __name__ == "__main__":
    est = get_estimator()
    est.fit()
    est.test()
    # tensorboard --logdir tf_logs
