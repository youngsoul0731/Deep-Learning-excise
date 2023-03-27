from torch.utils.data import Dataset, DataLoader
import cv2
import os
import glob
import torchvision.transforms as transforms
import random
import torch
import numpy as np
import matplotlib.pyplot as plt
from torch.utils.data import Dataset, DataLoader
import torch.nn as nn
import torch.nn.functional as F
import cv2
import os
import torchvision
from model import Generator,Discriminator
from torch.autograd import Variable
from torch.utils.tensorboard import SummaryWriter
workspace_dir = '.'


class FaceDataset(Dataset):
    def __init__(self, fnames, transform):
        self.transform = transform
        self.fnames = fnames
        self.num_samples = len(self.fnames)
    def __getitem__(self,idx):
        fname = self.fnames[idx]
        img = cv2.imread(fname)
        img = self.BGR2RGB(img) #because "torchvision.utils.save_image" use RGB
        img = self.transform(img)
        return img

    def __len__(self):
        return self.num_samples

    def BGR2RGB(self,img):
        return cv2.cvtColor(img,cv2.COLOR_BGR2RGB)


def get_dataset(path):
    fnames = glob.glob(path,recursive=True)
    # resize the image to (64, 64)
    # linearly map [0, 1] to [-1, 1]
    transform = transforms.Compose(
        [transforms.ToPILImage(),
         transforms.Resize((64, 64)),
         transforms.ToTensor(),
         transforms.Normalize(mean=[0.5] * 3, std=[0.5] * 3) ] )
    dataset = FaceDataset(fnames, transform)
    return dataset


def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        m.weight.data.normal_(0.0, 0.02)
    elif classname.find('BatchNorm') != -1:
        m.weight.data.normal_(1.0, 0.02)
        m.bias.data.fill_(0)


def same_seeds(seed):
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)  # if you are using multi-GPU.
    np.random.seed(seed)  # Numpy module.
    random.seed(seed)  # Python random module.
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True   
    
    
batch_size = 64
z_dim = 100
lr = 5e-04
n_epoch = 200
Diter_default=1 #Discriminator 每个iteration的训练次数
clamp_lower=-0.01
clamp_upper=0.01  #Discriminator权重clamp的上下限
save_dir = os.path.join(workspace_dir, 'logs')
os.makedirs(save_dir, exist_ok=True)



path="./**/*.jpg"   #这里跑原代码出错因此修改过，如果这里报错，请根据glob函数修改
dataset = get_dataset(path)    
dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
same_seeds(0)
input = torch.FloatTensor(batch_size, 3, 64, 64).cuda()
noise = torch.randn(100, z_dim).cuda()
one = torch.FloatTensor([1]).cuda()
mone = (one * -1).cuda()
#prepare model
G = Generator(in_dim=z_dim).cuda()
D = Discriminator(3).cuda()
G.train()
D.train()

#prepare optimizer
opt_D = torch.optim.RMSprop(D.parameters(), lr=lr) #优化器不能用Momentum及Adam，效果不好
opt_G = torch.optim.RMSprop(G.parameters(), lr=lr)

#train
z_sample=torch.randn(100, z_dim).cuda()
for epoch in range(n_epoch):
    for i,data in enumerate(dataloader):
        ############################
        # (1) Update D network
        ###########################
        for p in D.parameters(): # reset requires_grad
            p.requires_grad = True # they are set to False below in netG update

        # train the discriminator Diters times
        Diters = Diter_default
        j = 0
        while j < Diters :
            j += 1
            # clamp parameters to a cube
            for p in D.parameters():
                p.data.clamp_(clamp_lower,clamp_upper)
            # train with real
            
            real_cpu = data
            bs = real_cpu.size(0)
            noisev = torch.randn(bs, z_dim).cuda()
            D.zero_grad()

            real_cpu = real_cpu.cuda()
            input.resize_as_(real_cpu).copy_(real_cpu)
            inputv = Variable(input)

            errD_real = D(inputv)
            

            # train with fake
            with torch.no_grad():
                fake = Variable(G(noisev).data)
            inputv = fake
            errD_fake = D(inputv) # totally freeze netG
            errD = -errD_real + errD_fake
            errD.backward()
            opt_D.step()

        ############################
        # (2) Update G network
        ###########################
        for p in D.parameters():
            p.requires_grad = False # to avoid computation
        G.zero_grad()
        # in case our last batch was the tail batch of the dataloader,
        # make sure we feed a full batch of noise
        fake = G(noisev)
        errG = -D(fake)
        errG.backward()
        opt_G.step()
        i+=1

        # log
        print(f'\rEpoch [{epoch+1}/{n_epoch}] {i+1}/{len(dataloader)} Loss_D: {errD.data[0]:.4f} Loss_G: {errG.data[0]:.4f} \
            Loss_D_real: {errD_real.data[0]:.4f} Loss_D_fake: {errD_fake.data[0]:.4f}', end='')
    G.eval()
    with torch.no_grad():
        f_imgs_sample = (G(noise).data + 1) / 2.0
    filename = os.path.join(save_dir, f'Epoch_{epoch+1:03d}.jpg')
    torchvision.utils.save_image(f_imgs_sample, filename, nrow=10)
    print(f' | Save some samples to {filename}.')
    # show generated image
    grid_img = torchvision.utils.make_grid(f_imgs_sample.cpu(), nrow=10)
    plt.figure(figsize=(10,10))
    plt.imshow(grid_img.permute(1, 2, 0))
    plt.show()
    G.train()
    if (epoch+1) % 5 == 0:
        torch.save(G.state_dict(), os.path.join(workspace_dir, f'dcgan_g.pth'))
        torch.save(D.state_dict(), os.path.join(workspace_dir, f'dcgan_d.pth'))