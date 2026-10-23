"""Create clearly synthetic controls for the interview; never overwrites a folder."""
import argparse
import json
import math
import random
from pathlib import Path
from PIL import Image


def create(destination):
    destination.mkdir(parents=True, exist_ok=False)
    labels = {}
    for name, count, elongated in [('01-round', 35, 0), ('02-elongated', 35, 35),
                                    ('03-mixed', 35, 14), ('04-sparse', 4, 4), ('05-no-stars', 0, 0)]:
        width, height = 512, 384
        rng = random.Random(407)
        pixels = [.08 + .08*x/width + rng.uniform(-.002, .002) for y in range(height) for x in range(width)]
        positions = [(x, y) for y in range(64, 321, 64) for x in range(64, 449, 64)]
        for i, (cx, cy) in enumerate(positions[:count]):
            a, b = (3.0, 1.25) if i < elongated else (1.5, 1.5)
            for y in range(cy-18, cy+19):
                for x in range(cx-18, cx+19):
                    pixels[y*width+x] += .5*math.exp(-.5*((x-cx)**2/a**2 + (y-cy)**2/b**2))
        image = Image.new('L', (width, height))
        image.putdata([round(min(1, max(0, value))*255) for value in pixels])
        image.save(destination / (name + '.png'))
        labels[name + '.png'] = {'synthetic': True, 'sources': count, 'elongated_sources': elongated,
                                'input_axis_ratio': 2.4 if elongated else 1.0,
                                'expected_decision': 'insufficient_evidence' if count < 8 else
                                    'review_suggested' if elongated/count >= .4 else 'no_elongation_flag'}
    (destination / 'labels.json').write_text(json.dumps(labels, indent=2), encoding='utf-8')
    print(f'Created synthetic controls at {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    create(parser.parse_args().destination)
