import os
from network import *
from dataset import *
from utils import *
import torch
import torch.nn as nn
import argparse
import PIL
import openpifpaf

torch.manual_seed(0)

def load_pifpaf():
    print('Loading Pifpaf')
    net_cpu, _ = openpifpaf.network.factory.Factory(checkpoint='shufflenetv2k30', download_progress=False).factory()
    net = net_cpu.to(device)
    openpifpaf.decoder.utils.CifSeeds.threshold = 0.5
    openpifpaf.decoder.utils.nms.Keypoints.keypoint_threshold = 0.0
    openpifpaf.decoder.utils.nms.Keypoints.instance_threshold = 0.2   #main one
    openpifpaf.decoder.utils.nms.Keypoints.keypoint_threshold_rel = 0.0
    openpifpaf.decoder.CifCaf.force_complete = True
    decoder = openpifpaf.decoder.factory([hn.meta for hn in net_cpu.head_nets])
    preprocess = openpifpaf.transforms.Compose([
    openpifpaf.transforms.NormalizeAnnotations(),
    openpifpaf.transforms.CenterPadTight(16),
    openpifpaf.transforms.EVAL_TRANSFORM,
])
    return net, decoder, preprocess

# Parser

parser = argparse.ArgumentParser(description='Training and evaluating on Kitti')

# parameters

parser.add_argument('--model', '-m', type=str, help='model path', default='./models/')
parser.add_argument('--image', '-im', type=str, help='image path')
parser.add_argument('--out', '-o', type=str, help='out image path', default='./out_images/')
parser.add_argument('--pose', '-p', type=str, help='pose type', default="full")
parser.add_argument('--add_kps', '-kps', help='save the model', action='store_true')
parser.add_argument('--add_gt', '-gt', help='add ground truthl', action='store_true')
parser.add_argument('--gt_file', '-gt_f', type=str, help='ground truth path, if applicable', default='./test.jpg.predictions.json')

args = parser.parse_args()

pose = args.pose

use_cuda = torch.cuda.is_available()
device = torch.device("cuda:0" if use_cuda else "cpu")
print('Device: ', device)

if pose == "head":
	INPUT_SIZE = 15
elif pose == "body":
	INPUT_SIZE = 36
else:
	INPUT_SIZE = 51


net, processor, preprocess = load_pifpaf()

#model = LookingModel(INPUT_SIZE).to(device)
#model.load_state_dict(torch.load(args.m))
model = torch.load(args.model, map_location=device)
model.eval()

# Load the image

pil_im = PIL.Image.open(args.image).convert('RGB')
data = openpifpaf.datasets.PilImageList([pil_im], preprocess=preprocess)
loader = torch.utils.data.DataLoader(data, batch_size=1, pin_memory=True, collate_fn=openpifpaf.datasets.collate_images_anns_meta)
for images_batch, _, __ in loader:
	predictions = processor.batch(net, images_batch, device=device)[0]
	tab_predict = [p.json_data() for p in predictions]

# Run the predictions

img = cv2.imread(args.image)
if args.add_gt:
	path_gt = './gt_pred/'+args.image+'.json'
	data_gt = json.load(open(path_gt, 'r'))
	img_pred = run_and_rectangle_saved(img, tab_predict, data_gt, model, device)
else:
	img_pred = run_and_rectangle(img, tab_predict, model, device)
if args.add_kps:
    img_pred = run_and_kps(img_pred, tab_predict)
basename, _ = os.path.splitext(os.path.basename(args.image))
path_out = args.out + basename + '.prediction.png'
print(f'Saved image in {path_out}')
cv2.imwrite(args.out+args.image[:-4]+'.prediction.png', img_pred)
