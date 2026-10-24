package com.ptmcp;

/** Typed evidence that PT explicitly rejected authentication, rather than a timeout. */
final class AuthenticationRejectedException extends IllegalStateException {
    AuthenticationRejectedException(String message) {super(message);}
}
