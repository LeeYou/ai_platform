"""EfficientNet-B0 binary classifier for real-vs-fake portrait detection.

Output convention:
  logit  > 0  →  fake  (label 1)
  logit  < 0  →  real  (label 0)
  sigmoid(logit) = P(fake)

Migrated from LeeYou/recapture_detect (dev branch) for ai_platform integration.
"""

import torch
import torch.nn as nn
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0


class DesktopRecaptureDetector(nn.Module):
    """EfficientNet-B0 with a single-logit binary head."""

    def __init__(self, pretrained: bool = True):
        super().__init__()
        weights = EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        backbone = efficientnet_b0(weights=weights)

        # in_features = 1280 for EfficientNet-B0
        in_features = backbone.classifier[1].in_features
        backbone.classifier = nn.Identity()

        self.backbone   = backbone
        self.classifier = nn.Sequential(
            nn.Dropout(p=0.3),
            nn.Linear(in_features, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Return raw logit tensor of shape (B,)."""
        features = self.backbone(x)
        return self.classifier(features).squeeze(1)

    @torch.no_grad()
    def predict(self, x: torch.Tensor,
                threshold: float = 0.5) -> tuple:
        """Single-sample inference convenience wrapper.

        Returns:
            label      (int)   0 = real, 1 = fake
            confidence (float) probability of the predicted class
        """
        self.eval()
        logit      = self(x)
        prob_fake  = torch.sigmoid(logit).item()
        is_fake    = prob_fake >= threshold
        confidence = prob_fake if is_fake else (1.0 - prob_fake)
        return int(is_fake), float(confidence)
