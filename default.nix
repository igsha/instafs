{ stdenv, lib, python3Packages }:

let
  versionRegex = ".*__version__ = '([[:digit:]\\.]+)'.*";
  fileContent = builtins.readFile ./instafs/__init__.py;
  version = builtins.head (builtins.match versionRegex fileContent);

in python3Packages.buildPythonApplication {
  pname = "instafs";
  inherit version;

  src = ./.;

  propagatedBuildInputs = with python3Packages; [ requests fuse setuptools ];

  doCheck = false;

  meta = {
    description = "A fuse-based filesystem to get access to instagram";
    homepage = https://github.com/igsha/instafs;
    license = lib.licenses.mit;
    maintainers = with lib.maintainers; [ igsha ];
  };
}
