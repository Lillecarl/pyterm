# Where every source comes from. One entry per name.
#
# This file is the specification and a human writes it. `nix/sources.lock`
# holds the revisions and a tool writes it. Nothing reads this file to build:
# `nix/inputs.nix` joins the two.
#
# Fields:
#
#   url     The repository, over https. https is what a clone with no key can
#           reach, so it is what a CI runner and a fresh checkout get. A user
#           who pushes over SSH sets it once in their own gitconfig:
#
#             git config --global url."git@github.com:".insteadOf \
#               "https://github.com/"
#
#   branch  What `umbrella update` follows when it writes a new revision.
#
#   path    Where a working copy of this source goes: the directory beside
#           this file's parent, named after the source. `umbrella fetch`
#           clones there and `umbrella update` refuses when the two disagree.
#
#           When the directory holds anything, `nix/resolve.nix` reads that
#           checkout at the revision the lock names, so a build here and a
#           build in CI agree. UMBRELLA_DEV names the sources to read as
#           directories instead, and `.envrc` sets it to `all`, because the
#           loop here is to edit a working copy and build without committing.
#
#           The test is the contents, not the directory. A fresh clone has
#           none of them until `umbrella fetch` runs.
{
  # The six that are the code.
  pyte = {
    url = "https://github.com/Lillecarl/pyte.git";
    branch = "graphics-protocol";
    path = ../pyte;
  };
  ptyhost = {
    url = "https://github.com/Lillecarl/ptyhost.git";
    branch = "main";
    path = ../ptyhost;
  };
  ptterm = {
    url = "https://github.com/Lillecarl/ptterm.git";
    branch = "graphics-protocol";
    path = ../ptterm;
  };
  txterm = {
    url = "https://github.com/Lillecarl/txterm.git";
    branch = "main";
    path = ../txterm;
  };
  pymux = {
    url = "https://github.com/Lillecarl/pymux.git";
    branch = "graphics-protocol";
    path = ../pymux;
  };

  # The toolkit under ptterm and pymux. Every patch here has to be one
  # upstream could take, which is why it is a branch of upstream's name and
  # not a fork of ours.
  prompt-toolkit = {
    url = "https://github.com/Lillecarl/python-prompt-toolkit.git";
    branch = "render-performance";
    path = ../prompt-toolkit;
  };

  # The test equipment the suites share.
  pyterm-pytest = {
    url = "https://github.com/Lillecarl/pyterm-pytest.git";
    branch = "main";
    path = ../pyterm-pytest;
  };

  # The tool that holds the other seven together. It is a source like the
  # rest, so it can be edited in place.
  umbrella = {
    url = "https://github.com/Lillecarl/umbrella.git";
    branch = "main";
    path = ../umbrella;
  };

  # The builders that assemble a virtualenv, instead of nixpkgs' propagation
  # and PYTHONPATH. Lillecarl/pymux#319.
  #
  # No `path`: this is somebody else's repository and we do not edit it, so
  # there is no working copy to read. `nix/resolve.nix` answers from the lock
  # alone when a source names no path.
  pyproject-nix = {
    url = "https://github.com/pyproject-nix/pyproject.nix.git";
    branch = "master";
  };
}
