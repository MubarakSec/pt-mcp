package com.ptmcp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Objects;
import java.nio.file.attribute.PosixFilePermission;

/**
 * Pure save-target handling for {@code pt_save_file}.
 *
 * Saving to an existing Packet Tracer file asks PT to show an "Overwrite
 * File?" modal. Packet Tracer's IPC layer does not expose a reliable way to
 * confirm that dialog, so the overwrite path writes to a unique temporary
 * sibling first and only then replaces the target. The temporary file is
 * deliberately left behind when any step fails so evidence is not lost.
 */
final class SaveFilePolicy {

    /** Raised when the requested target already exists and overwrite was not granted. */
    static final class TargetExistsException extends IllegalArgumentException {
        TargetExistsException(String message) {
            super(message);
        }
    }

    /** A validated save plan. tempPath is null when the target is safe to write directly. */
    record SavePlan(Path target, Path savePath, Path tempPath, boolean overwrite,
                    java.util.Set<PosixFilePermission> permissions) {
    }

    private SaveFilePolicy() {
    }

    static SavePlan prepare(String rawPath, boolean overwrite) {
        if (rawPath == null || rawPath.trim().isEmpty()) {
            throw new IllegalArgumentException("path es obligatorio.");
        }
        Path target = Paths.get(rawPath.trim());
        if (!target.isAbsolute()) {
            throw new IllegalArgumentException("path debe ser absoluto, no '" + rawPath + "'.");
        }
        String fileName = target.getFileName() == null ? "" : target.getFileName().toString();
        if (!fileName.toLowerCase().endsWith(".pkt")) {
            throw new IllegalArgumentException("path debe terminar en .pkt, no '" + rawPath + "'.");
        }
        Path parent = target.toAbsolutePath().normalize().getParent();
        if (parent == null || !Files.isDirectory(parent)) {
            throw new IllegalArgumentException("directorio no existe o no es un directorio: "
                    + (parent == null ? rawPath : parent) + ".");
        }
        boolean exists = Files.exists(target, java.nio.file.LinkOption.NOFOLLOW_LINKS);
        if (exists) {
            // Never follow a symlink or replace a directory by accident.
            if (Files.isSymbolicLink(target) || Files.notExists(target)
                    || !Files.isRegularFile(target, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                throw new IllegalArgumentException("target debe ser un archivo regular .pkt; no se sobreescribe: "
                        + rawPath + ".");
            }
            if (!overwrite) {
                throw new TargetExistsException("target ya existe; usa overwrite=true para reemplazarlo.");
            }
            if (!Files.isWritable(parent)) {
                throw new IllegalArgumentException("directorio no es escribible: " + parent + ".");
            }
            Path temp = uniqueTempPath(parent);
            return new SavePlan(target, temp, temp, true, permissions(target));
        }
        if (!Files.isWritable(parent)) {
            throw new IllegalArgumentException("directorio no es escribible: " + parent + ".");
        }
        return new SavePlan(target, target, null, false, null);
    }

    /** Replace the target with the verified temporary save. No effect for a fresh target. */
    static void complete(SavePlan plan) throws IOException {
        Objects.requireNonNull(plan, "plan");
        if (plan.tempPath() == null) {
            return;
        }
        if (!Files.isRegularFile(plan.tempPath(), java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("el archivo temporal no existe o no es regular: " + plan.tempPath().toString());
        }
        applyPermissions(plan.tempPath(), plan.permissions());
        try {
            Files.move(plan.tempPath(), plan.target(),
                    StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(plan.tempPath(), plan.target(), StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static Path uniqueTempPath(Path parent) {
        for (int attempt = 0; attempt < 1000; attempt++) {
            Path temp = parent.resolve("pt-mcp-save-" + java.util.UUID.randomUUID() + ".pkt");
            if (Files.notExists(temp, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                return temp;
            }
        }
        throw new IllegalArgumentException("no se pudo generar un nombre temporal unico para " + parent + ".");
    }

    private static java.util.Set<PosixFilePermission> permissions(Path target) {
        try {
            return Files.getPosixFilePermissions(target);
        } catch (UnsupportedOperationException | IOException e) {
            return null;
        }
    }

    private static void applyPermissions(Path path, java.util.Set<PosixFilePermission> permissions) {
        if (permissions == null) {
            return;
        }
        try {
            Files.setPosixFilePermissions(path, permissions);
        } catch (UnsupportedOperationException | IOException e) {
            // Permissions are best-effort; the rename must still happen.
        }
    }
}
