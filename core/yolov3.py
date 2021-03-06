"""
Reference: 

Ayoosh Kathuria https://github.com/ayooshkathuria/YOLO_v3_tutorial_from_scratch/blob/master/darknet.py
YunYang1994 https://github.com/YunYang1994/tensorflow-yolov3/blob/master/core/yolov3.py
"""


import tensorflow as tf
from tensorflow.keras import Model
from tensorflow.keras.layers import BatchNormalization, Conv2D, Input, ZeroPadding2D, LeakyReLU, UpSampling2D
from core.utils import configManager

physical_devices = tf.config.experimental.list_physical_devices('GPU')
tf.config.experimental.set_memory_growth(physical_devices[0], True)

def convolutional(inputs, blocks, block, i, filters):
    activation = block["activation"]
    filters = int(block["filters"])
    kernel_size = int(block["size"])
    strides = int(block["stride"])

    if strides > 1:
        inputs = ZeroPadding2D(((1, 0), (1, 0)))(inputs)

    inputs = Conv2D(filters,
                    kernel_size,
                    strides=strides,
                    padding='valid' if strides > 1 else 'same',
                    name='conv_' + str(i),
                    use_bias=False if ("batch_normalize" in block) else True)(inputs)

    if "batch_normalize" in block:
        inputs = BatchNormalization(name='bnorm_' + str(i))(inputs)
    if activation == "leaky":
        inputs = LeakyReLU(alpha=0.1, name='leaky_' + str(i))(inputs)

    return inputs, filters, block

def upsample(inputs, block):
    stride = int(block["stride"])
    inputs = UpSampling2D(stride)(inputs)
    return inputs, block

def route(input, block, outputFilters, outputs, i):
    block["layers"] = block["layers"].split(',')
    start = int(block["layers"][0])

    if len(block["layers"]) > 1:
       end = int(block["layers"][1]) - i
       filters = outputFilters[i + start] + outputFilters[end] 
       inputs = tf.concat([outputs[i + start], outputs[i + end]], axis=-1)
    else:
       filters = outputFilters[i + start]
       inputs = outputs[i + start]
   
    return inputs, filters, outputs, outputFilters, block

def shortcut(inputs, block, outputs, i):
    from_ = int(block["from"])
    inputs = outputs[i - 1] + outputs[i + from_]
    return inputs, outputs, block

def yolo(inputs, block, num_classes, input_image, outPred, filters, scale, i):
    mask = block["mask"].split(",")
    mask = [int(x) for x in mask]
    anchors = block["anchors"].split(",")
    anchors = [int(a) for a in anchors]
    anchors = [(anchors[i], anchors[i + 1]) for i in range(0, len(anchors), 2)]
    anchors = [anchors[i] for i in mask]

    n_anchors = len(anchors)

    out_shape = inputs.get_shape().as_list()

    inputs = tf.reshape(inputs, [-1, n_anchors * out_shape[1] * out_shape[2], \
										 5 + num_classes])

    box_centers = inputs[:, :, 0:2]
    box_shapes = inputs[:, :, 2:4]
    confidence = inputs[:, :, 4:5]
    classes = inputs[:, :, 5:num_classes + 5]

    box_centers = tf.sigmoid(box_centers)
    confidence = tf.sigmoid(confidence)
    classes = tf.sigmoid(classes)

    anchors = tf.tile(anchors, [out_shape[1] * out_shape[2], 1])
    box_shapes = tf.exp(box_shapes) * tf.cast(anchors, dtype=tf.float32)

    x = tf.range(out_shape[1], dtype=tf.float32)
    y = tf.range(out_shape[2], dtype=tf.float32)

    cx, cy = tf.meshgrid(x, y)
    cx = tf.reshape(cx, (-1, 1))
    cy = tf.reshape(cy, (-1, 1))
    cxy = tf.concat([cx, cy], axis=-1)
    cxy = tf.tile(cxy, [1, n_anchors])
    cxy = tf.reshape(cxy, [1, -1, 2])

    strides = (input_image.shape[1] // out_shape[1], \
               input_image.shape[2] // out_shape[2])
    box_centers = (box_centers + cxy) * strides

    prediction = tf.concat([box_centers, box_shapes, confidence, classes], axis=-1)

    if scale:
        outPred = tf.concat([outPred, prediction], axis=1)
    else:
        outPred = prediction
        scale = 1

    return inputs, filters, outPred, scale

def build(cfgfile, model_size, num_classes):

    blocks = configManager(cfgfile)

    outputs = {}
    outputFilters = []
    filters = []
    outPred = []
    scale = 0

    inputs = input_image = Input(shape=model_size)
    inputs = inputs / 255.0

    for i, block in enumerate(blocks[1:]):
        if (block["type"] == "convolutional"):
            inputs, filters, block = convolutional(inputs, blocks, block, i, filters)

        elif (block["type"] == "upsample"):
            inputs, block = upsample(inputs, block)

        elif (block["type"] == "route"):
            inputs, filters, outputs, outputFilters, block = route(input, block, outputFilters, outputs, i)

        elif block["type"] == "shortcut":
            inputs, outputs, block = shortcut(inputs, block, outputs, i)

        elif block["type"] == "yolo":
            inputs, filters, outPred, scale = yolo(inputs, block, num_classes, input_image, outPred, filters, scale, i)

        outputs[i] = inputs
        outputFilters.append(filters)

    model = Model(input_image, outPred)
    model.summary()
    return model



