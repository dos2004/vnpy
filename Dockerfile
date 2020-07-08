# Set the base image
FROM ubuntu:18.04
MAINTAINER vnpy.loopring

RUN apt-get update && \
  apt-get install -y software-properties-common

# Install linux dependencies
RUN apt-get update && \
    apt-get install -y gcc \
    build-essential pkg-config libusb-1.0 curl git sudo wget libsqlite3-dev locales

RUN curl -LO http://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh
RUN bash Miniconda3-latest-Linux-x86_64.sh -p /miniconda -b
RUN rm Miniconda3-latest-Linux-x86_64.sh
ENV PATH=/miniconda/bin:${PATH}
RUN conda update -y conda

# update pip
RUN python -m pip install pip --upgrade
#RUN python -m pip install wheel

# Copy files
RUN mkdir -p /home/miner/vnpy
COPY . /home/miner/vnpy
ENV PYTHONPATH=/home/miner/vnpy
WORKDIR /home/miner/vnpy
RUN ["bash", "install.sh"]

CMD ["python", "../example/no_ui/run.py"]
