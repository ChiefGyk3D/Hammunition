- **`requires_java`: a plan-time Java floor measured with `java -version`**
  (**D-037**, amended 2026-10-02). `default-jre-headless` is a metapackage that
  says nothing about the Java major, so GraphHopper (17, from its pom and the
  jar's class-file major) planned cleanly on Ubuntu 22.04 and Pop!_OS 22.04 and
  failed at run time. A manifest names `requires_java`; the plan runs `java
  -version` once and defers a profile member, or refuses a typed unit, below the
  floor, stating the measured version and the archive's `openjdk-N-jre-headless`
  that would meet it. Nothing is fetched. BRouter is set to 11, its measured
  build target (the ruling said 17; the build file says 11).
