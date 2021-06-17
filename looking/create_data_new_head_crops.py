from PIL import Image
import os
import numpy as np
import json
from tqdm import tqdm
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

## Helper functions

def convert_file_to_data(file):
	data = {"path":[], "bbox":[], "names":[], "Y":[], "video":[]}
	for line in file:
		line = line[:-1]
		line_s = line.split(",")
		path = line_s[0]+'/'+line_s[2].zfill(5)+'.png'
		Y = int(line_s[-1])
		bbox = [float(line_s[3]), float(line_s[4]), float(line_s[5]), float(line_s[6])]
		data['path'].append(path)
		data["bbox"].append(bbox)
		data['Y'].append(Y)
		data['names'].append(line_s[1])
		data["video"].append(line_s[0])
	return data

def enlarge_bbox(bb, enlarge=1):
	delta_h = (bb[3]) / (7 * enlarge)
	delta_w = (bb[2]) / (3.5 * enlarge)
	bb[0] -= delta_w
	bb[1] -= delta_h
	bb[2] += delta_w
	bb[3] += delta_h
	return bb

def convert_bb(bb):
	return [bb[0], bb[1], bb[0]+bb[2], bb[1]+bb[3]]

def convert_kps(data):
	X = []
	Y = []
	C = []
	A = []
	i = 0
	while i < 51:
		X.append(data[i])
		Y.append(data[i+1])
		C.append(data[i+2])
		i += 3
	A = np.array([X, Y, C]).flatten().tolist()
	return A


def bb_intersection_over_union(boxA, boxB):
	# determine the (x, y)-coordinates of the intersection rectangle
	xA = max(boxA[0], boxB[0])
	yA = max(boxA[1], boxB[1])
	xB = min(boxA[2], boxB[2])
	yB = min(boxA[3], boxB[3])

	# compute the area of intersection rectangle
	interArea = abs(max((xB - xA, 0)) * max((yB - yA), 0))
	if interArea == 0:
		return 0
	# compute the area of both the prediction and ground-truth
	# rectangles
	boxAArea = abs((boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
	boxBArea = abs((boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))

	# compute the intersection over union by taking the intersection
	# area and dividing it by the sum of prediction + ground-truth
	# areas - the interesection area
	iou = interArea / float(boxAArea + boxBArea - interArea)

	# return the intersection over union value
	return iou

def crop_head(img, kps):
    default_l = 10
    idx = [3, 4]
    candidate1, candidate2 = kps[3*idx[0]:3*idx[0]+2], kps[3*idx[1]:3*idx[1]+2]
    #candidate1, candidate2 = [kps[idx[0]], kps[17+idx[0]], kps[34+idx[0]]], [kps[idx[1]], kps[17+idx[1]], kps[34+idx[1]]]
    if candidate1[0] > candidate2[0]:
        kps1 = candidate2
        kps2 = candidate1
    else:
        kps1 = candidate1
        kps2 = candidate2
    # l is euclidean dist between keypoints
    l = np.linalg.norm(np.array(kps2)-np.array(kps1))
    if l < default_l:
        l = default_l

    bbox = [kps1[0]-0.5*max(l, default_l), kps1[1]-1*max(l, default_l), kps2[0]+0.5*max(l, default_l), kps2[1]+1*max(l, default_l)]
    for i in range(len(bbox)):
        if bbox[i] < 0:
            bbox[i] = 0
        else:
            bbox[i] = int(bbox[i])

    x1, y1, x2, y2 = bbox

    # No head in picture
    default_l = 5
    if x1 == img.shape[1]:
        x1 -= default_l
    if y1 == img.shape[0]:
        y1 -= default_l
    if x2 == 0:
        x2 += default_l
    if y2 == 0:
        y2 += default_l
    if x1 == x2:
        x2 += default_l
    if y1 == y2:
        y2 += default_l

    # shape img 1080*1920
    if y2 > img.shape[0]:
        y2 = img.shape[0]
    if x2 > img.shape[1]:
        x2 = img.shape[1]

    return img[int(y1):int(y2), int(x1):int(x2)]
# Cluster
path_jaad = "/work/vita/datasets/JAAD/images/"
path_joints = "/scratch/izar/caristan/data/jaad_pifpaf_new/"

dir_out = "./splits"
path_out = "/scratch/izar/caristan/data/JAAD_2k30_new_head/"



assert os.path.isdir(dir_out), "directory to save ground-truth not found"
assert os.path.isdir(path_out), "output directory to save crops not found"

file = open("results_new.csv", "r")

file_out = open(os.path.join(dir_out, "ground_truth_2k30_head_crop_pifpaf.txt"), "w+")

# Convert the data
data = convert_file_to_data(file)

name_pic = 0

for i in tqdm(range(len(data["Y"]))):
	path = data["path"][i]
	data_json = json.load(open(path_joints+path+'.predictions.json', 'r'))
	if len(data_json)> 0:
		iou_max = 0
		j = None
		bb_gt = data["bbox"][i]
		sc = 0
		for k in range(len(data_json)):
			di = data_json[k]
			bb = convert_bb(enlarge_bbox(di["bbox"]))
			iou = bb_intersection_over_union(bb, bb_gt)
			if iou > iou_max:
				iou_max = iou
				j = k
				bb_final = bb
				sc = di["score"]
		if iou_max > 0.3:
			kps = convert_kps(data_json[j]["keypoints"])
			name_head = str(name_pic).zfill(10)+'.png'
			img = Image.open(path_jaad+path).convert('RGB')
			img = np.asarray(img)
			head = crop_head(img, data_json[j]["keypoints"])
			Image.fromarray(head).convert('RGB').save(path_out+name_head)
			#print(path, path_out+name_head)
			kps_out = {"X":kps}
			if path in ['video_0223/00205.png', 'video_0313/00379.png']:
				print(path, name_head)
			json.dump(kps_out, open(path_out+name_head+'.json', "w"))
			line = path+','+data["names"][i]+','+str(bb_final[0])+','+str(bb_final[1])+','+str(bb_final[2])+','+str(bb_final[3])+','+str(sc)+','+str(iou_max)+','+name_head+','+str(data["Y"][i])+'\n'
			name_pic += 1
			file_out.write(line)
file_out.close()
file.close()
