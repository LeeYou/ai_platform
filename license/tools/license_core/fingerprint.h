#ifndef AGILESTAR_FINGERPRINT_H
#define AGILESTAR_FINGERPRINT_H

/**
 * fingerprint.h
 * Machine fingerprint collection.
 */

#include <string>

/// Collects hardware identifiers (board serial, UUID, first NIC MAC),
/// hashes them with SHA-256, and returns "sha256:<hex>".
std::string collect_fingerprint();

#endif /* AGILESTAR_FINGERPRINT_H */
