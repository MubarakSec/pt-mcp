package com.ptmcp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class SaveFilePolicyTest {

    private static final String TARGET = "lab.pkt";

    public static void main(String[] args) throws Exception {
        SaveFilePolicyTest test = new SaveFilePolicyTest();
        test.existingTargetWithoutOverwriteDoesNotTouchTarget();
        test.existingTargetWithOverwriteUsesTempThenReplaces();
        test.missingTargetSavesDirectly();
        test.rejectsRelativePath();
        test.rejectsWrongExtension();
        test.rejectsMissingParent();
        test.rejectsDirectoryTarget();
        test.rejectsSymlinkTarget();
        test.completeWithoutTempPreservesTarget();
        test.tempNameIsSafeAndSibling();
        System.out.println("SaveFilePolicyTest passed");
    }

    void existingTargetWithoutOverwriteDoesNotTouchTarget() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path target = dir.resolve(TARGET);
        Files.writeString(target, "original");
        try {
            SaveFilePolicy.prepare(target.toString(), false);
            throw new AssertionError("expected TargetExistsException");
        } catch (SaveFilePolicy.TargetExistsException e) {
            assertEquals("existing target error should name overwrite=true",
                    "target ya existe", e.getMessage().split(";")[0]);
        }
        assertEquals("target must remain unchanged", "original", Files.readString(target));
    }

    void existingTargetWithOverwriteUsesTempThenReplaces() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path target = dir.resolve(TARGET);
        Files.writeString(target, "original");
        SaveFilePolicy.SavePlan plan = SaveFilePolicy.prepare(target.toString(), true);
        if (plan.tempPath() == null) throw new AssertionError("expected temporary save path");
        assertEquals("temp must be created beside the target", dir.normalize(),
                plan.tempPath().getParent().normalize());
        Files.writeString(plan.tempPath(), "replacement");
        SaveFilePolicy.complete(plan);
        assertEquals("target must contain the temporary save", "replacement", Files.readString(target));
        if (Files.exists(plan.tempPath())) throw new AssertionError("temporary file must be moved");
    }

    void missingTargetSavesDirectly() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path target = dir.resolve(TARGET);
        SaveFilePolicy.SavePlan plan = SaveFilePolicy.prepare(target.toString(), true);
        assertEquals("fresh target must not use a temporary sibling", null, plan.tempPath());
        assertEquals("save path must be the target", target, plan.savePath());
        SaveFilePolicy.complete(plan); // no-op for a fresh target
        if (Files.exists(target)) throw new AssertionError("prepare must not create the target");
    }

    void rejectsRelativePath() throws Exception {
        expectIllegalArgument(() -> SaveFilePolicy.prepare("relative.pkt", false), "path debe ser absoluto");
    }

    void rejectsWrongExtension() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path target = dir.resolve("lab.xml");
        expectIllegalArgument(() -> SaveFilePolicy.prepare(target.toString(), false), "terminar en .pkt");
    }

    void rejectsMissingParent() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path target = dir.resolve("missing").resolve(TARGET);
        expectIllegalArgument(() -> SaveFilePolicy.prepare(target.toString(), false), "directorio no existe");
    }

    void rejectsDirectoryTarget() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path directory = dir.resolve("directory.pkt");
        Files.createDirectory(directory);
        expectIllegalArgument(() -> SaveFilePolicy.prepare(directory.toString(), true), "archivo regular");
    }

    void rejectsSymlinkTarget() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path real = dir.resolve("real.pkt");
        Files.writeString(real, "original");
        Path link = dir.resolve(TARGET);
        Files.createSymbolicLink(link, real);
        expectIllegalArgument(() -> SaveFilePolicy.prepare(link.toString(), true), "archivo regular");
        assertEquals("symlink target must remain", "original", Files.readString(real));
    }

    void completeWithoutTempPreservesTarget() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path target = dir.resolve(TARGET);
        Files.writeString(target, "original");
        SaveFilePolicy.SavePlan plan = new SaveFilePolicy.SavePlan(target, target,
                target.resolveSibling("missing-temp.pkt"), true, null);
        try {
            SaveFilePolicy.complete(plan);
            throw new AssertionError("expected IOException");
        } catch (IOException expected) {
            // The target must be untouched when the temporary save is missing.
        }
        assertEquals("target must survive a failed replace", "original", Files.readString(target));
        Files.deleteIfExists(plan.tempPath());
    }

    void tempNameIsSafeAndSibling() throws Exception {
        Path dir = Files.createTempDirectory("pt-mcp-save-");
        Path target = dir.resolve(TARGET);
        Files.writeString(target, "original");
        SaveFilePolicy.SavePlan plan = SaveFilePolicy.prepare(target.toString(), true);
        String name = plan.tempPath().getFileName().toString();
        if (!name.startsWith("pt-mcp-save-") || !name.endsWith(".pkt")) {
            throw new AssertionError("unsafe temp name: " + name);
        }
        assertEquals("temp sibling must stay in the target directory", dir.normalize(),
                plan.tempPath().getParent().normalize());
        Files.deleteIfExists(plan.tempPath());
    }


    private static void expectIllegalArgument(ThrowingRunnable runnable, String messagePart) throws Exception {
        try {
            runnable.run();
            throw new AssertionError("expected IllegalArgumentException containing " + messagePart);
        } catch (IllegalArgumentException e) {
            if (e instanceof SaveFilePolicy.TargetExistsException) {
                throw e;
            }
            if (!e.getMessage().toLowerCase().contains(messagePart.toLowerCase())) {
                throw new AssertionError("unexpected message: " + e.getMessage());
            }
        }
    }

    private static void assertEquals(String message, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(message + ": expected " + expected + " but was " + actual);
        }
    }

    private interface ThrowingRunnable {
        void run() throws Exception;
    }
}
