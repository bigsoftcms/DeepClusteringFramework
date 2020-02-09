import logging
from typing import Dict

import torch
import numpy

from allennlp.models.model import Model
from allennlp.modules import TokenEmbedder, TextFieldEmbedder
from allennlp.nn.util import get_text_field_mask
from overrides import overrides

from allennlp.data.vocabulary import Vocabulary
from allennlp.modules.seq2vec_encoders import Seq2VecEncoder
from allennlp.modules.seq2seq_decoders import SeqDecoder

from clustering_tool.modules.clusterers.clusterer import Clusterer
from clustering_tool.modules.losses import AutoencoderLoss
from clustering_tool.modules.metrics.NormalizedMutualInformation import NormalizedMutualInformation

logger = logging.getLogger(__name__)


@Model.register("deep_clustering")
class DeepClusteringModel(Model):
    """
    Performs deep embedding clustering using given loss
    """

    def __init__(self, vocab: Vocabulary,
                 encoder : Seq2VecEncoder,
                 clusterer: Clusterer,
                 num_clusters,
                 num_classes = None,
                 decoder: SeqDecoder = None,
                 autoencoder_loss: AutoencoderLoss = None,
                 embedders: TextFieldEmbedder = None):
        """

        :param vocab:
        :param encoder: an encoder f(x): X -> H of input x; Maps high dimension x into low dimension h to cluster
        :param decoder: a decoder g(h) H -> X; maps encoder output back to sample's initial high - dimension space
        :param clusterer: computes soft cluster assignments s for given h
        :param autoencoder_loss: a joint autoencoder and clusterer loss; TODO maybe separate clusterer and autoencoder loss? Move clustering loss into clusterer
        :param embedder: an input sequence token embedder. Must not be trainable
        """

        super(DeepClusteringModel, self).__init__(vocab)

        self._encoder = encoder
        self._decoder = decoder
        self._clusterer = clusterer
        self._autoencoder_loss = autoencoder_loss
        self._embedders = embedders

        #self.nmi = NormalizedMutualInformation(num_clusters, num_classes if num_classes else num_clusters)

    @overrides
    def forward(self, sentence, label = None):

        mask = get_text_field_mask(sentence)
        if self._embedders:
            x = self._embedders(sentence)
        else:
            embedded_representations = []
            for key, value in sentence.items():
                embedded_representations.append(value)
            x = torch.cat(embedded_representations, dim=-1)

        # shape: (batch_size, bottleneck_embedding_size)
        h = self._encoder(x, mask)
        # shape: (batch_size, clusters_num)
        clusterer_out = self._clusterer(x, h)

        output_dict = {'h': h, 's': clusterer_out['s'], 'loss': clusterer_out['loss']}

        if label is not None:
            # shape: (batch_size, max_seq_length, input_embedding_size)
            if self._decoder or self._autoencoder_loss:
                if self._decoder is None or self._autoencoder_loss is None:
                    raise RuntimeError("Decoder and autoencoder loss must be provided together")

                decoded_x = self._decoder(h)
                if self._autoencoder_loss:
                    output_dict["loss"] += self._autoencoder_loss(x, h, decoded_x)

            #self.nmi(output_dict['s'], label)

        return output_dict

    def decode(self, output_dict: Dict[str, torch.Tensor]):
        cluster_labels = output_dict['s'].argmax(axis=-1)
        output_dict['cluster'] = cluster_labels
        return output_dict

    #def get_metrics(self, reset: bool = False):
     #   return {"nmi": self.nmi.get_metric(reset)}




