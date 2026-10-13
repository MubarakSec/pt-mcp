# Third-party provenance and notices

This file records the origin of included or locally supplied components. It does not grant rights beyond the licenses provided by each upstream project or vendor.

## Python saved-file toolkit

The crypto implementation in `Decipher/` is vendored from [Punkcake21/Unpacket](https://github.com/Punkcake21/Unpacket) and is identified by its upstream project as MIT-licensed. The vendored files retain their copyright and license notices where supplied.

## Java live backend

The Java backend is based on [jenaro1804/PacketTracer_mcp](https://github.com/jenaro1804/PacketTracer_mcp), upstream commit `9cc8112dd8e67ce406f3786373725965fae56c14`. The former Java checkout records local integration work at commit `a17ea90`; its source is now bundled under `backend/java/`. The upstream checkout inspected for this integration contained no `LICENSE` file. No license is inferred here; consult the upstream author/repository for licensing status before redistributing that code.

The Java build also resolves dependencies declared in `backend/java/build.gradle` from Maven Central. Consult each dependency's own license and metadata for its terms.

## Cisco Packet Tracer components

The `pt-cep-java-framework-9.0.0.0.jar` and Cisco `meta` executable are obtained from a local Packet Tracer installation by `setup.py`. The JAR is copied into the ignored `backend/java/libs/` directory for local builds; it is not included in this repository. Packet Tracer and Cisco components remain subject to Cisco's terms. The generated `.pta`, XML registration file, local credentials, and build output are local setup artifacts and are not versioned.

## Historical evidence

Verification files record behavior from particular local Packet Tracer, JDK, SDK, and backend snapshots. They are test evidence, not third-party software or a compatibility guarantee. See [LIVE-SETUP.md](LIVE-SETUP.md) for the documented verification scope.
