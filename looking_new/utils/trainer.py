import configparser
from utils.dataset import *
from utils.network import *
from utils.losses import *
import os, errno
import seaborn as sns
import matplotlib.pyplot as plt
import copy
from torch.utils.data.sampler import WeightedRandomSampler

class Parser():
	"""
		Class definition for parser in order to get the right arguments
	"""
	def __init__(self, config):
		self.general = config['General']
		self.model_type = config['Model_type']
		self.eval_params = config['Eval']
		self.data_args = config['Dataset']
		self.multi_args = config['Multi_Dataset']
		self.jaad_args = config['JAAD_dataset']
		self.kitti_args = config['Kitti_dataset']
		self.nu_args = config['Nuscenes_dataset']
		self.jack_args = config['JackRabbot_dataset']
		use_cuda = torch.cuda.is_available()
		self.device = torch.device("cuda" if use_cuda else "cpu")
		print('Device: ', self.device)

	def get_model(self):
		criterion_type = self.general['loss']
		optimizer_type = self.general['optimizer']
		self.data_transform = None
		self.grad_map = False
		self.eval_it = int(self.general['eval_it'])
		self.dropout = float(self.general['dropout'])
		self.multi_dataset = self.general.getboolean('multi_dataset')
		self.weighted = self.multi_args.getboolean('weighted')
		assert criterion_type in ['BCE', 'focal_loss']
		assert optimizer_type in ['adam', 'sgd']
		if criterion_type == 'BCE':
			criterion = nn.BCELoss()
		else:
			criterion = FocalLoss(alpha=1, gamma=3)

		# Select model type
		model_type = self.model_type['type']
		pose = self.general['pose']
		self.grad_map = None
		assert model_type in ['joints', 'heads', 'eyes', 'fullbodies', 'heads+joints', 'eyes+joints', 'fullbodies+joints']
		assert pose in ['head', 'body', 'full']
		# Joints
		if model_type == 'joints':
			self.grad_map = self.general.getboolean('grad_map')
			if pose == "head":
				INPUT_SIZE = 15
			elif pose == "body":
				INPUT_SIZE = 36
			else:
				INPUT_SIZE = 51
			model = LookingModel(INPUT_SIZE, self.dropout).to(self.device)
		# Eyes
		elif model_type == 'eyes':
			self.data_transform = transforms.Compose([
					SquarePad(),
					transforms.ToTensor(),
				transforms.ToPILImage(),
					transforms.Resize((10,15)),
				transforms.ToTensor(),
				transforms.Normalize(mean=[0.485, 0.456, 0.406],
									std=[0.229, 0.224, 0.225])])
			INPUT_SIZE = 450
			model = LookingModel(INPUT_SIZE, self.dropout).to(self.device)
		# Heads or Fullbodies
		elif model_type == 'heads' or model_type == 'fullbodies':
			backbone = self.model_type['backbone']
			fine_tune = self.model_type.getboolean('fine_tune')
			assert backbone in ['alexnet', 'resnet18', 'resnet50']
			if backbone == 'alexnet':
				model = AlexNet_head(self.device, fine_tune)
				self.data_transform = transforms.Compose([
						SquarePad(),
						transforms.ToTensor(),
					transforms.ToPILImage(),
						transforms.Resize((256,256)),
					transforms.ToTensor(),
						transforms.Normalize(mean=[0.485, 0.456, 0.406],
											std=[0.229, 0.224, 0.225])])
			elif backbone == 'resnet18':
				model = ResNet18_head(self.device)
				self.data_transform = transforms.Compose([
						SquarePad(),
						transforms.ToTensor(),
					transforms.ToPILImage(),
						transforms.Resize((224,224)),
					transforms.ToTensor(),
						transforms.Normalize(mean=[0.485, 0.456, 0.406],
											std=[0.229, 0.224, 0.225])
				])
			else:
				model = ResNet50_head(self.device)
				self.data_transform = transforms.Compose([
						SquarePad(),
						transforms.ToTensor(),
					transforms.ToPILImage(),
						transforms.Resize((224,224)),
					transforms.ToTensor(),
						transforms.Normalize(mean=[0.485, 0.456, 0.406],
											std=[0.229, 0.224, 0.225])
				])
		# Multimodels
		else:
			backbone = self.model_type['backbone']
			fine_tune = self.model_type.getboolean('fine_tune')
			if 'eyes' in model_type:
				self.data_transform = transforms.Compose([
						SquarePad(),
						transforms.ToTensor(),
					transforms.ToPILImage(),
						transforms.Resize((10,15)),
					transforms.ToTensor(),
					transforms.Normalize(mean=[0.485, 0.456, 0.406],
										std=[0.229, 0.224, 0.225])])
				INPUT_SIZE = 450
				model = LookingModel(INPUT_SIZE, self.dropout).to(self.device)
			else:
				self.data_transform = transforms.Compose([
							SquarePad(),
							transforms.ToTensor(),
						transforms.ToPILImage(),
							transforms.Resize((224,224)),
						transforms.ToTensor(),
							transforms.Normalize(mean=[0.485, 0.456, 0.406],
												std=[0.229, 0.224, 0.225])
				])
			assert backbone in ['resnet18', 'resnet50']
			if self.model_type['trained_on'] == 'JAAD':
				name_model_joints = '_'.join(['LookingModel', criterion.__class__.__name__, self.general['pose'], self.data_args['split']])+'.pkl'
				if backbone == 'resnet18':
					name_model_backbone = '_'.join(['ResNet18_' + model_type.split('+')[0], criterion.__class__.__name__, self.data_args['split']])+'.pkl'
				else:
					name_model_backbone = '_'.join(['ResNet50_' + model_type.split('+')[0], criterion.__class__.__name__, self.data_args['split']])+'.pkl'
			else:
				name_model_joints = '_'.join(['LookingModel', criterion.__class__.__name__, self.general['pose'], ''])+'.pkl'
				if backbone == 'resnet18':
					name_model_backbone = '_'.join(['ResNet18_' + model_type, criterion.__class__.__name__, ''])+'.pkl'
				else:
					name_model_backbone = '_'.join(['ResNet50_' + model_type, criterion.__class__.__name__, ''])+'.pkl'
			path_output_model_backbone = os.path.join(self.general['path'], self.model_type['trained_on'], 'Heads')
			path_backbone = os.path.join(path_output_model_backbone, name_model_backbone)

			path_output_model_joints = os.path.join(self.general['path'], self.model_type['trained_on'], 'Joints')
			path_model_joints = os.path.join(path_output_model_joints, name_model_joints)
			print(path_backbone)
			print(path_model_joints)
			if fine_tune:
				if not os.path.isfile(path_backbone):
					print('ERROR: Heads model not trained, please train your heads model first')
					exit(0)
				if not os.path.isfile(path_model_joints):
					print('ERROR: Joints model not trained, please train your joints model first')
					exit(0)

			if backbone == 'resnet18':
				model = LookingNet_early_fusion_18(path_backbone, path_model_joints, self.device, fine_tune)
			else:
				model = LookingNet_early_fusion_50(path_backbone, path_model_joints, self.device, fine_tune)

		# Set parameters for training
		self.model_type_ = model_type
		self.pose = pose
		self.lr = float(self.general['learning_rate'])
		self.epochs = int(self.general['epochs'])
		self.batch_size = int(self.general['batch_size'])
		if optimizer_type == 'adam':
			optimizer = torch.optim.Adam(model.parameters(), lr=self.lr)
		else:
			if fine_tune and model_type=='heads' or model_type=='fullbodies':
				optimizer = torch.optim.SGD(model.net.classifier.parameters(), lr=self.lr, momentum=0.9)
			else:
				optimizer = torch.optim.SGD(model.parameters(), lr=self.lr, momentum=0.9)
		return model, criterion, optimizer, self.data_transform

	def get_data(self, data_type):
		split_strategy = self.data_args['split']
		if self.multi_dataset:
			dataset_names = data_type.split(',')
			paths_txt = [os.path.join(self.data_args['path_txt'], 'splits_'+data_name.lower()) for data_name in dataset_names]
			dataset_train = []
			dataset_val = []
			for path_txt in paths_txt:
				if 'nu' in path_txt:
					path_data = self.nu_args['path_data']
					dataset_train.append(Jack_Nu_dataset('nu', 'train', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device))
					dataset_val.append(Jack_Nu_dataset('nu', 'val', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device))
				elif 'jack' in path_txt:
					path_data = self.jack_args['path_data']
					dataset_train.append(Jack_Nu_dataset('jack', 'train', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device))
					dataset_val.append(Jack_Nu_dataset('jack', 'val', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device))
				elif 'jaad' in path_txt:
					path_data = self.jaad_args['path_data']
					dataset_train.append(JAAD_Dataset(path_data, self.model_type_, 'train', self.pose, split_strategy, self.data_transform, path_txt, self.device))
					dataset_val.append(JAAD_Dataset(path_data, self.model_type_, 'val', self.pose, split_strategy, self.data_transform, path_txt, self.device))
				elif 'kitti' in path_txt:
					path_data = self.kitti_args['path_data']
					dataset_train.append(Kitti_dataset('train', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device))
					dataset_val.append(Kitti_dataset('val', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device))
			return dataset_train, dataset_val

		else:
			path_txt = os.path.join(self.data_args['path_txt'], 'splits_'+data_type.lower())
			dataset_train = []
			dataset_val = []

			if data_type == 'JAAD':
				path_data = self.data_args['path_data']
				dataset_train = JAAD_Dataset(path_data, self.model_type_, 'train', self.pose, split_strategy, self.data_transform, path_txt, self.device)
				dataset_val = JAAD_Dataset(path_data, self.model_type_, 'val', self.pose, split_strategy, self.data_transform, path_txt, self.device)
			elif data_type == 'Kitti':
				path_data = self.data_args['path_data']
				dataset_train = Kitti_dataset('train', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
				dataset_val = Kitti_dataset('val', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
			elif data_type == 'Nu':
				path_data = self.data_args['path_data']
				dataset_train = Jack_Nu_dataset('nu', 'train', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
				dataset_val = Jack_Nu_dataset('nu', 'val', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
			else:
				path_data = self.data_args['path_data']
				dataset_train = Jack_Nu_dataset('jack', 'train', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
				dataset_val = Jack_Nu_dataset('jack', 'val', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
			return dataset_train, dataset_val

	def get_data_test(self, data_type):
		split_strategy = self.eval_params['split']
		path_txt = os.path.join(self.data_args['path_txt'], 'splits_'+data_type.lower())
		print(path_txt)
		dataset_test = []
		path_data = self.eval_params['path_data_eval']
		if data_type == 'JAAD':
			dataset_test = JAAD_Dataset(path_data, self.model_type_, 'test', self.pose, split_strategy, self.data_transform, path_txt, self.device)
		elif data_type == 'Kitti':
			dataset_test = Kitti_dataset('test', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
		elif data_type == 'Jack':
			dataset_test = Jack_Nu_dataset('jack', 'test', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
		elif data_type == 'Nu':
			dataset_test = Jack_Nu_dataset('nu', 'test', self.model_type_, path_txt, path_data, self.pose, self.data_transform, self.device)
		return dataset_test

	def parse(self):
		self.model, self.criterion, self.optimizer, self.data_transform = self.get_model()
		if self.multi_dataset:
			names = '+'.join(self.multi_args['train_datasets'].split(','))

			self.path_output = os.path.join(self.general['path'], names, self.model_type['type'].title())
			self.dataset_train, self.dataset_val = self.get_data(self.multi_args['train_datasets'])
			self.path_output = os.path.join(self.general['path'], names, self.model_type['type'].title())
			try:
				os.makedirs(self.path_output)
			except OSError as e:
				if e.errno != errno.EEXIST:
					raise

			features = [self.model.__class__.__name__, self.criterion.__class__.__name__]
			if self.model_type['type'] == 'joints':
				features.append(self.general['pose'])

			if 'JAAD' in names:
				features.append('{}'.format(self.data_args['split']))

			if self.weighted:
				features.append('weighted')



			name_model = '_'.join(features)+'.pkl'
			#else:
			#    name_model = '_'.join([self.model.__class__.__name__, self.criterion.__class__.__name__, self.general['pose']].extend(additional_features))+'.p'
			self.path_model = os.path.join(self.path_output, name_model)

		else:
			self.dataset_train, self.dataset_val = self.get_data(self.data_args['name'])
			self.path_output = os.path.join(self.general['path'], self.data_args['name'], self.model_type['type'].title())
			try:
				os.makedirs(self.path_output)
			except OSError as e:
				if e.errno != errno.EEXIST:
					raise

			additional_features = ''
			if 'JAAD' in self.data_args['name']:
				additional_features += '{}'.format(self.data_args['split'])

			if self.model_type['type'] != 'joints':
				name_model = '_'.join([self.model.__class__.__name__, self.criterion.__class__.__name__, additional_features])+'.pkl'
			else:
				name_model = '_'.join([self.model.__class__.__name__, self.criterion.__class__.__name__, self.general['pose'], additional_features])+'.pkl'
			self.path_model = os.path.join(self.path_output, name_model)
			if self.grad_map:
				self.out_grad = self.path_model[:-2]+'_grads.png'

	def load_model_for_eval(self):
		self.model.load_state_dict(torch.load(self.path_model))
		self.model = self.model.to(self.device).eval()

class Evaluator():
	"""
		Class definition for evaluation. To run once you have the traind model
	"""
	def __init__(self, parser):
		self.parser = parser
		use_cuda = torch.cuda.is_available()
		self.device = torch.device("cuda" if use_cuda else "cpu")
		print(self.parser.path_model)
		if os.path.isfile(self.parser.path_model):
			print('Model file exists.. Loading model file ...')
			self.parser.load_model_for_eval()
		else:
			print('ERROR : Model file doesnt exists, please train your model first or review your parameters')
			exit(0)
		self.height_ = self.parser.eval_params.getboolean('height')
	def evaluate_distance(self):
		ap, acc, ap_1, ap_2, ap_3 = data_test.evaluate(self.parser.model, self.device, 10, True)
		print('Far : {} | Middle : {} | Close :{}'.format(ap_1, ap_2, ap_3))
		print('Evaluation on {} | acc:{:.1f} | ap:{:.1f}'.format(data_to_evaluate, acc, ap*100))

	def evaluate(self):
		"""
			Loop over the test set and evaluate the performance of the model on it
		"""
		data_to_evaluate = self.parser.eval_params['eval_on']
		data_test = self.parser.get_data_test(data_to_evaluate)
		"""data_loader_test = DataLoader(data_test, 1, shuffle=False)
		if data_to_evaluate not in ['JAAD', 'NU']:
			acc = 0
			ap = 0

			output_all = torch.Tensor([]).type(torch.float).to(self.parser.device)
			labels_all = torch.Tensor([]).to(self.parser.device)
			for x_batch, y_batch in data_loader_test:

				y_batch = y_batch.to(self.parser.device)
				output = self.parser.model(x_batch)

				pred_label = torch.round(output)

				labels_all = torch.cat((labels_all.detach().cpu(), y_batch.detach().cpu().view(-1)), dim=0)
				output_all = torch.cat((output_all.detach().cpu(), output.view(-1).detach().cpu()), dim=0)

			ap = average_precision(output_all, labels_all)
			acc = binary_acc(output_all.type(torch.float).view(-1), labels_all).item()
		else:"""
		if self.height_==False:
			ap, acc = data_test.evaluate(self.parser.model, self.device, 10)
			print('Evaluation on {} | acc:{:.1f} | ap:{:.1f}'.format(data_to_evaluate, acc, ap*100))
		else:
			ap, acc, ap_1, ap_2, ap_3, ap_4, distances = data_test.evaluate(self.parser.model, self.device, 10, True)

			print('Distances : ', np.mean(distances, axis=0))
			print('Ap Far : {:.1f} | Middle 1 : {:.1f} | Middle_2 : {:.1f} | Close :{:.1f}'.format(ap_1*100, ap_2*100, ap_3*100, ap_4*100))
			#print('Ac Far : {:.1f} | Middle 1 : {:.1f} | Middle_2 : {:.1f} | Close :{:.1f}'.format(ac_1*100, ac_2*100, ac_3*100, ac_4*100))
			print('Evaluation on {} | acc:{:.1f} | ap:{:.1f}'.format(data_to_evaluate, acc, ap*100))



class Trainer():
	"""
		Class definition for training and saving the trained model
	"""
	def __init__(self, parser):
		self.parser = parser
		self.get_grads = parser.grad_map
		use_cuda = torch.cuda.is_available()
		self.device = torch.device("cuda" if use_cuda else "cpu")
	def get_sampler(self, concat_dataset):
		weigths = 1./ torch.Tensor([len(data) for data in concat_dataset])
		di = {}
		for i, data in enumerate(self.parser.dataset_train):
			di[data.name] = weigths[i]
		weigths_samples = []
		for data in self.parser.dataset_train:
			for _ in data:
				weigths_samples.append(di[data.name])
		sampler = WeightedRandomSampler(torch.Tensor(weigths_samples), len(weigths_samples))
		return sampler

	def train(self):
		self.parser.model = self.parser.model.to(self.device).train()
		if self.parser.multi_dataset:
			concat_dataset = torch.utils.data.ConcatDataset(self.parser.dataset_train)
			if self.parser.weighted:
				sampler = self.get_sampler(concat_dataset)
				train_loader = DataLoader(concat_dataset, batch_size=self.parser.batch_size, sampler=sampler, drop_last=True)
			else:
				train_loader = DataLoader(concat_dataset, batch_size=self.parser.batch_size, shuffle=True, drop_last=True)
		else:
			train_loader = DataLoader(self.parser.dataset_train, batch_size=self.parser.batch_size, shuffle=True, drop_last=True)
		running_loss = 0
		i = 0
		best_ap = 0
		best_ac = 0
		grads_x = []
		grads = []

		for epoch in range(self.parser.epochs):
			#self.parser.model = self.parser.model.train().to(self.parser.device)
			losses = []
			accuracies = []

			for x_batch, y_batch in train_loader:

				y_batch = y_batch.to(self.device)
				self.parser.optimizer.zero_grad()
				output = self.parser.model(x_batch)
				loss = self.parser.criterion(output, y_batch.float())
				running_loss += loss.item()

				loss.backward()
				losses.append(loss.item())
				accuracies.append(binary_acc(output.type(torch.float), y_batch).item())

				self.parser.optimizer.step()
				i += 1

				if i%10 == 0:
					print_summary_step(i, np.mean(losses), np.mean(accuracies))
					losses = []
					accuracies = []

			i = 0
			best_ap, best_ac, ap_val, acc_val = self.eval_epoch(best_ap, best_ac)
			print('')
			print('Epoch {} | mAP_val : {} | mAcc_val :{}'.format(epoch+1, ap_val, acc_val))

			if self.get_grads:
				grads_x = []
				self.parser.optimizer.zero_grad()
				model = copy.deepcopy(self.parser.model).to('cpu').eval()
				for joints, labels in DataLoader(self.parser.dataset_train, batch_size=len(self.parser.dataset_train), drop_last=True):
					joints, labels = joints.to('cpu'), labels.to('cpu').type(torch.float)
					break
				joints.requires_grad=True
				error = nn.BCELoss()(model(joints), labels)
				error.backward()
				for g in joints.grad.data:
					grads_x.append(g)
				outs1 = torch.stack(grads_x,1)
				grads.append(torch.mean(abs(outs1), axis=1))
				joints, labels = None, None
				error = None
				model = None
				torch.cuda.empty_cache()
		if self.get_grads:
			res = torch.stack(grads,1)
			y_labels = ['nose', 'left_eye','right_eye','left_ear','right_ear','left_shoulder','right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist','left_hip','right_hip','left_knee','right_knee','left_ankle','right_ankle','nose', 'left_eye','right_eye','left_ear','right_ear','left_shoulder','right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist','left_hip','right_hip','left_knee','right_knee','left_ankle','right_ankle','nose', 'left_eye','right_eye','left_ear','right_ear','left_shoulder','right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist','left_hip','right_hip','left_knee','right_knee','left_ankle','right_ankle']
			grads_magnitude = res
			grads_magnitude_ = grads_magnitude[:17, :]+grads_magnitude[17:34, :]+grads_magnitude[34:, :]
			ax = sns.heatmap(grads_magnitude_, linewidth=0.5, yticklabels=y_labels[:17], xticklabels=list(range(1, self.parser.epochs+1)))
			#for i, x in enumerate(ax.get_xticklabels()):
			#    if i%5 == 0:
			#        x_ticks.append(x)
			ax.set_yticklabels(ax.get_ymajorticklabels(), fontsize = 6)
			ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize = 6)
			plt.xlabel("# Epochs")
			plt.savefig(self.parser.out_grad)
			plt.close()
			ax = sns.heatmap(grads_magnitude, linewidth=0.5, yticklabels=y_labels, xticklabels=list(range(1, self.parser.epochs+1)))
			ax.set_yticklabels(ax.get_ymajorticklabels(), fontsize = 6)
			ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize = 6)
			plt.xlabel("# Epochs")
			plt.savefig(self.parser.out_grad[:-5]+'_all.png')
			plt.close()


	def eval_epoch(self, best_ap, best_ac):
		self.parser.model = self.parser.model.eval()
		if self.parser.multi_dataset:
			tab_ap = []
			tab_acc = []
			for data in self.parser.dataset_val:
				aps, accs = data.evaluate(self.parser.model, self.device, it=self.parser.eval_it)
				tab_ap.append(aps)
				tab_acc.append(accs)
			#exit(0)
			aps, accs = np.mean(tab_ap), np.mean(tab_acc)
		else:
			aps, accs = self.parser.dataset_val.evaluate(self.parser.model, self.device, it=self.parser.eval_it)

		if aps > best_ap:
			best_ap = aps
			best_ac = accs
			torch.save(self.parser.model.state_dict(), self.parser.path_model)
		#self.parser.model = self.parser.model.train().to(self.parser.device)
		return best_ap, best_ac, aps, accs
