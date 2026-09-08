# CME FFmpeg Lambda Layer

The CDK stack builds this layer from the checksum-pinned Linux ARM64
`imageio-ffmpeg==0.6.0` wheel. `imageio-ffmpeg` is BSD-2-Clause licensed;
FFmpeg itself is subject to the license terms of the bundled build. The layer is
generated during CDK synthesis and is not committed.

The video processor uses `/opt/bin/ffmpeg` from this layer to produce timestamped
two-frames-per-second evidence stills for each extracted CME examination window.
