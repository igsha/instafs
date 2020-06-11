with import <nixpkgs> { };

let instafs = callPackage ./. {};
in mkShell {
  name = "instafs";
  buildInputs = instafs.propagatedBuildInputs;
  PYTHONDONTWRITEBYTECODE = 1;
}
