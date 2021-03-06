import argparse
import glob
import logging
import os

import natsort
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

from import_model import *


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epoch', type=int, default=100000,
                        help='epoch')
    parser.add_argument('--batch_size', type=int, default=1000,
                        help='batch_size')
    parser.add_argument('--lr', type=int, default=0.0001,
                        help='learning rate')

    parser.add_argument('--log_interval', type=int, default=10,
                        help='print log every n epoch')
    parser.add_argument('--save_interval', type=int, default=100,
                        help='save checkpoint every n epoch')

    parser.add_argument('--signal_len', type=int, default=60,
                        help='raw imput signal length, like tensor.shape==(N, 1, 60) is 60')
    parser.add_argument('--latent_dim', type=int, default=6,
                        help='latent dimension')

    parser.add_argument('--eval_val', type=bool, default=True,
                        help='if eval validation set (True | False)')
    parser.add_argument('--continue_training', type=bool, default=False,
                        help='if continue training (True | False)')
    parser.add_argument('--use_gpu', type=bool, default=True,
                        help='if use gpu (True | False)')
    parser.add_argument('--num_workers', type=int, default=0,
                        help='dataloader workers')

    args = parser.parse_args()
    args.device = torch.device('cuda' if args.use_gpu and torch.cuda.is_available() else 'cpu')
    return args


def logging_set():
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    file_handler = logging.FileHandler("log_training.log", mode='a')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[file_handler, stream_handler]
    )


def main():
    os.makedirs('model_saved', exist_ok=True)
    args = parse_args()
    args.train_file = 'normal.npy'
    logging.info(args)

    rris_np = np.load(args.train_file)
    all_set = TensorDataset(torch.as_tensor(rris_np).float())

    train_len = int(len(all_set) * 0.8)
    val_len = int(len(all_set) * 0.1)
    test_len = len(all_set) - train_len - val_len
    torch.manual_seed(0)
    split_shape = (train_len, val_len, test_len)
    train_set, val_set, test_set = random_split(all_set, split_shape)
    torch.seed()

    train_loader = DataLoader(
        dataset=train_set,
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=True,
        num_workers=args.num_workers
    )
    val_loader = DataLoader(dataset=val_set, batch_size=len(val_set))
    logging.info(f"training set length: {len(train_set)}")
    logging.info(f"validation set length: {len(val_set)}")
    logging.info(f"test set length: {len(test_set)}")

    model = AutoEncoder(args).to(args.device)
    logging.info(f'model structure:\n {model}')
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_func = nn.MSELoss()

    continue_epoch = 0
    if args.continue_training:
        try:
            checkpoint_fps = glob.glob('model_saved/checkpoint_*.pt')
            if len(checkpoint_fps) == 0:
                raise FileNotFoundError('no saved checkpoint files')
            checkpoint_fp = natsort.natsorted(checkpoint_fps)[-1]

            checkpoint = torch.load(checkpoint_fp, map_location=args.device)
            model.load_state_dict(checkpoint['model_state_dict'])
            optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            continue_epoch = checkpoint['epoch']
            continue_loss = checkpoint['loss']

            logging.info(f"load checkpoint file: '{checkpoint_fp}")
            logging.info((
                f"continue epoch: {continue_epoch}",
                f"train_loss: {continue_loss.data.cpu().numpy():.10f}",
            ))
        except:
            logging.exception('load model checkpoint failed')
        logging.info(f'continue training from epoch: {continue_epoch}')

    model.train()
    for epoch in range(continue_epoch, args.epoch):
        for step, (x,) in enumerate(train_loader):
            x = x.to(args.device)
            encoded, decoded = model(x)

            loss = loss_func(decoded, x)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        if epoch % args.log_interval == 0:
            if not args.eval_val:
                val_loss = torch.tensor(-1)
            else:
                with torch.no_grad():
                    model.eval()
                    for val_x, in val_loader:
                        val_x = val_x.to(args.device)

                        val_encoded, val_decoded = model(val_x)
                        val_loss = loss_func(val_decoded, val_x)
                    model.train()

            logging.info((
                f"epoch: {epoch}",
                f"total_step: {epoch * len(train_loader) + step}",
                f"train_loss: {loss.data.cpu().numpy():.10f}",
                f"val_loss: {val_loss.cpu().numpy():.10f}"
            ))

        if epoch % args.save_interval == 0:
            torch.save({
                'epoch': epoch,
                'loss': loss,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
            }, f'model_saved/checkpoint_epoch_{epoch}.pt')
    torch.save({
        'epoch': epoch,
        'loss': loss,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
    }, f'model_saved/checkpoint_epoch_{epoch}.pt')


if __name__ == "__main__":
    logging_set()
    main()
