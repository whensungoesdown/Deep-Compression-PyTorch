import argparse
import os

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from tqdm import tqdm

from net.models import LeNet
from net.quantization import apply_weight_sharing
import util

from torch.utils.tensorboard import SummaryWriter


# Writer will output to ./runs/ directory by default
writer = SummaryWriter()

os.makedirs('saves', exist_ok=True)

# Training settings
parser = argparse.ArgumentParser(description='PyTorch MNIST pruning from deep compression paper')
#parser.add_argument('--batch-size', type=int, default=50, metavar='N',
parser.add_argument('--batch-size', type=int, default=50, metavar='N',
                    help='input batch size for training (default: 50)')
parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                    help='input batch size for testing (default: 1000)')
parser.add_argument('--epochs', type=int, default=100, metavar='N',
                    help='number of epochs to train (default: 100)')
parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                    help='learning rate (default: 0.01)')
parser.add_argument('--no-cuda', action='store_true', default=False,
                    help='disables CUDA training')
parser.add_argument('--seed', type=int, default=42, metavar='S',
                    help='random seed (default: 42)')
parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                    help='how many batches to wait before logging training status')
parser.add_argument('--log', type=str, default='log.txt',
                    help='log file name')
parser.add_argument('--sensitivity', type=float, default=0.25,
                    help="sensitivity value that is multiplied to layer's std in order to get threshold value")
args = parser.parse_args()

# Control Seed
torch.manual_seed(args.seed)

# Select Device
use_cuda = not args.no_cuda and torch.cuda.is_available()
device = torch.device("cuda" if use_cuda else 'cpu')
if use_cuda:
    print("Using CUDA!")
    torch.cuda.manual_seed(args.seed)
else:
    print('Not using CUDA!!!')

# Loader
kwargs = {'num_workers': 5, 'pin_memory': True} if use_cuda else {}
train_loader = torch.utils.data.DataLoader(
    datasets.MNIST('data', train=True, download=True,
                   transform=transforms.Compose([
                       transforms.ToTensor(),
                       transforms.Normalize((0.1307,), (0.3081,))
                   ])),
    batch_size=args.batch_size, shuffle=True, **kwargs)
test_loader = torch.utils.data.DataLoader(
    datasets.MNIST('data', train=False, transform=transforms.Compose([
                       transforms.ToTensor(),
                       transforms.Normalize((0.1307,), (0.3081,))
                   ])),
    batch_size=args.test_batch_size, shuffle=False, **kwargs)


# Define which model to use
model = LeNet(mask=True).to(device)

print(model)
util.print_model_parameters(model)




def add_100_to_10 (a):

    b = torch.empty(10, dtype=torch.float)
    b.fill_(0)

    for i in range(10):
        for j in range(10):
            b[i].add_(a[i*10+j])

    return b

def add_100_to_10_batch50 (a):

    b = torch.empty(50, 10, dtype=torch.float)
    b.fill_(0)

    for batch in range(50):
        for i in range(10):
            for j in range(10):
                b[batch, i].add_(a[batch, i*10+j])
                                                                    
    return b


# NOTE : `weight_decay` term denotes L2 regularization loss term
optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=0.0001)

# uty: test
#scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.95)
scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=100, gamma=0.10)

initial_optimizer_state_dict = optimizer.state_dict()

# uty: test original model training only needs 100 epochs
def train(epochs):
    model.train()
    for epoch in range(epochs):
#    for epoch in range(100):
        pbar = tqdm(enumerate(train_loader), total=len(train_loader))
        for batch_idx, (data, target) in pbar:
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output_tuple = model(data)
            output = output_tuple[2]
            # uty: test
            #print("!!!!!!!!")
            #print(output_tuple[0].size())
            #print(output_tuple[1].size())
            #print(output_tuple[2].size())
            #print(output_tuple[3].size())
            #print('!!!!!!')
            #print(type(output))
            #print(batch_idx)
            #print(output)
            #print(target)
            loss = F.nll_loss(output, target)
            loss.backward()


            #grads = []
            # zero-out all the gradients corresponding to the pruned connections
            for name, p in model.named_parameters():
               # print("name: ")
               # print(name)
               # print("p: ")
               # print(p)
               # print("p.grad: ")
               # print(p.grad)
                if 'fc2.weight' in name:
                    fc2_grads = p.grad
                    #print("fc2_grads: ")
                    #print(fc2_grads)

                if 'mask' in name:
                    continue
                tensor = p.data.cpu().numpy()
                grad_tensor = p.grad.data.cpu().numpy()
                grad_tensor = np.where(tensor==0, 0, grad_tensor)
                p.grad.data = torch.from_numpy(grad_tensor).to(device)
                #np.append(grads, p.grad.data.cpu().numpy())

            #grads.append(p.grad.data.cpu().numpy())

            #print("grads: ")
            #print(grads)
            #grads = optimizer.compute_gradients(output)
            #grads = np.array(grads)
#            writer.add_histogram('original/fc2_gradients', fc2_grads, global_step=batch_idx, bins='tensorflow')

            optimizer.step()
            if batch_idx % args.log_interval == 0:
                done = batch_idx * len(data)
                percentage = 100. * batch_idx / len(train_loader)
                pbar.set_description(f'Train Epoch: {epoch} [{done:5}/{len(train_loader.dataset)} ({percentage:3.0f}%)]  Loss: {loss.item():.6f}')
                writer.add_histogram('orig.loss', loss.item(), global_step=epochs, bins='tensorflow')
        

def train_without_modeltrain(epochs):
#    model.train()
    for epoch in range(epochs):
        pbar = tqdm(enumerate(train_loader), total=len(train_loader))
        for batch_idx, (data, target) in pbar:
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            # uty: test
            #output_tuple = model(data)
            #output = output_tuple[2]
            #loss = F.nll_loss(output, target)
            #loss.backward()

            output_tuple = model(data)
            orig_output_tuple = uty_model_orig(data)
            ##loss = nn.MSELoss(output_tuple[0], orig_output_tuple[0], reduction='sum') + nn.MSELoss(output_tuple[1], orig_output_tuple[1], reduction='sum')

            #try only l2
            #loss_l1 = nn.MSELoss(reduction='mean');
            #output_l1 = loss_l1(output_tuple[0], orig_output_tuple[0])

            loss_l1 = nn.MSELoss(reduction='sum');
            output_l1 = loss_l1(output_tuple[0], orig_output_tuple[0])

            loss_l2 = nn.MSELoss(reduction='sum');
            output_l2 = loss_l2(output_tuple[1], orig_output_tuple[1])
            #output_l2 = loss_l2(add_100_to_10_batch50(output_tuple[1]), add_100_to_10_batch50(orig_output_tuple[1]))

            loss_l3 = nn.MSELoss(reduction='sum');
            output_l3 = loss_l3(output_tuple[3], orig_output_tuple[3])

            #output = output_l1 + output_l2;
            output = output_l1 + output_l2 + output_l3;
            output.backward()


            #grads = np.array()
            # zero-out all the gradients corresponding to the pruned connections
            for name, p in model.named_parameters():
                if 'fc2.weight' in name:
                    fc2_grads = p.grad

                if 'mask' in name:
                    continue
                tensor = p.data.cpu().numpy()
                grad_tensor = p.grad.data.cpu().numpy()
                grad_tensor = np.where(tensor==0, 0, grad_tensor)
                p.grad.data = torch.from_numpy(grad_tensor).to(device)
                #np.append(grads, p.grad.data.cpu().numpy())
           
            #grads = optimizer.compute_gradients(output)
#            writer.add_histogram('prune/fc2_gradients', fc2_grads, global_step=batch_idx, bins='tensorflow')

            optimizer.step()
            if batch_idx % args.log_interval == 0:
                done = batch_idx * len(data)
                percentage = 100. * batch_idx / len(train_loader)
                #pbar.set_description(f'Train Epoch: {epoch} [{done:5}/{len(train_loader.dataset)} ({percentage:3.0f}%)]  Loss: {loss.item():.6f}')
                pbar.set_description(f'Train Epoch: {epoch} [{done:5}/{len(train_loader.dataset)} ({percentage:3.0f}%)]  Loss: {output.item():.6f}')
                writer.add_histogram('prune.loss', output.item(), global_step=epochs, bins='tensorflow')

        scheduler.step()

def test():
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            # uty: test
            output_tuple = model(data)
            output = output_tuple[2]

            test_loss += F.nll_loss(output, target, reduction='sum').item() # sum up batch loss
            pred = output.data.max(1, keepdim=True)[1] # get the index of the max log-probability
            correct += pred.eq(target.data.view_as(pred)).sum().item()

        test_loss /= len(test_loader.dataset)
        accuracy = 100. * correct / len(test_loader.dataset)
        print(f'Test set: Average loss: {test_loss:.4f}, Accuracy: {correct}/{len(test_loader.dataset)} ({accuracy:.2f}%)')
    return accuracy


# Initial training
print("--- Initial training ---")
train(args.epochs)
accuracy = test()
util.log(args.log, f"initial_accuracy {accuracy}")
torch.save(model, f"saves/initial_model.ptmodel")
print("--- Before pruning ---")
util.print_nonzeros(model)

# uty: test copy a model instance for later reference

uty_model_orig = type(model)(mask=True)
uty_model_orig.load_state_dict(model.state_dict()) # copy weights and stuff


print("!!!test")
print(model)
print(uty_model_orig)
print("\n")


# Pruning
model.prune_by_std(args.sensitivity)
accuracy = test()
util.log(args.log, f"accuracy_after_pruning {accuracy}")
print("--- After pruning ---")
util.print_nonzeros(model)

# uty test
# Retrain
print("--- Retraining ---")
optimizer.load_state_dict(initial_optimizer_state_dict) # Reset the optimizer
#train(args.epochs)
train_without_modeltrain(args.epochs)


writer.close()

torch.save(model, f"saves/model_after_retraining.ptmodel")
accuracy = test()
#util.log(args.log, f"accuracy_after_retraining {accuracy}")
util.log(args.log, f"uty: no retraining, accuracy_after_retraining {accuracy}")

print("--- After Retraining ---")
util.print_nonzeros(model)
