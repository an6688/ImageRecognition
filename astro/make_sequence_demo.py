"""Create a clearly labeled synthetic time sequence, never real-world validation."""
import argparse
from pathlib import Path
import cv2
import numpy as np


def generate(folder):
    folder.mkdir(parents=True, exist_ok=False)
    rng=np.random.default_rng(42)
    y,x=np.mgrid[:360,:480]
    stars=list(zip(rng.integers(30,450,90),rng.integers(30,330,90),rng.uniform(.15,.65,90)))
    labels=['baseline','baseline_noise','transient_streak','dimmed_exposure','elongated_sources','baseline_return']
    for i,label in enumerate(labels):
        image=np.full((360,480),.035,np.float32)
        for cx,cy,peak in stars:
            image += peak*np.exp(-((x-cx)**2/(18 if i==4 else 5)+(y-cy)**2/5))
        if i==2:cv2.line(image,(70,80),(390,240),.7,1)
        if i==3:image *= .55
        image += rng.normal(0,.003,image.shape).astype(np.float32)
        matrix=cv2.getRotationMatrix2D((240,180),i*.15,1)
        matrix[:,2] += (i*.7,-i*.4)
        image=cv2.warpAffine(image,matrix,(480,360))
        cv2.imwrite(str(folder/f'{i+1:02d}_{label}.png'),np.rint(np.clip(image,0,1)*65535).astype(np.uint16))
    (folder/'README.txt').write_text('SYNTHETIC CONTROL SEQUENCE. Gaussian sources, known small motions, noise, one transient streak, dimming, and elongation. Not real sky photographs or detector accuracy evidence.\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    generate(parser.parse_args().folder)
