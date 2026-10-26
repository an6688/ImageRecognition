import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from sequence import align, build, prepare


def sky():
    rng = np.random.default_rng(91)
    image = np.full((192, 256), .025, np.float32)
    y, x = np.mgrid[:192, :256]
    for cx, cy, peak in zip(rng.integers(15, 240, 55), rng.integers(15, 175, 55), rng.uniform(.15, .7, 55)):
        image += peak*np.exp(-((x-cx)**2+(y-cy)**2)/5.)
    return np.clip(image, 0, 1)


class SequenceTests(unittest.TestCase):
    def test_known_motion_and_valid_borders(self):
        anchor=sky()
        matrix=cv2.getRotationMatrix2D((128,96), 1.5, 1)
        matrix[:,2] += (3,-2)
        moving=cv2.warpAffine(anchor,matrix,(256,192))
        aligned, valid, info=align(anchor,moving)
        self.assertLess(np.mean(np.abs(aligned[valid]-anchor[valid])), .008)
        self.assertGreater(info['correlation'], .95)
        self.assertFalse(valid.all())
        self.assertAlmostEqual(abs(info['angle']), 1.5, delta=.2)

    def test_unrelated_blank_and_different_dimensions(self):
        for other in [np.zeros((192,256),np.float32),np.random.default_rng(77).random((192,256),dtype=np.float32),np.zeros((64,64),np.float32)]:
            with self.assertRaises(ValueError):align(sky(),other)

    def test_folder_errors_escaping_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'input';folder.mkdir()
            image=np.rint(sky()*65535).astype(np.uint16)
            cv2.imwrite(str(folder/'01.png'),image)
            cv2.imwrite(str(folder/'02 & test.png'),image)
            (folder/'03.jpg').write_bytes(b'bad file')
            cv2.imwrite(str(folder/'04.png'),np.zeros((24,24),np.uint8))
            data=build(folder,root/'report.html','A < B',256)
            self.assertEqual(len(data['frames']),2)
            self.assertEqual(len(data['rejected']),2)
            self.assertIn('A &lt; B',(root/'report.html').read_text(encoding='utf-8'))
            with self.assertRaises(ValueError):build(folder,root/'report.html')
            with self.assertRaises(ValueError):prepare(folder,limit=2)


if __name__=='__main__':unittest.main()
