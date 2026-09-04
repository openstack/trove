local controller = os.getenv("CONTROLLER")
local guest_id = os.getenv("guest_id")

local ssh_config = {
    identityFile = "/home/_GUEST_USERNAME_/.ssh/id_rsa",

    options = {
        UserKnownHostsFile = "/dev/null",
        StrictHostKeyChecking = "no",
        User = "_HOST_SCP_USERNAME_",
        LogLevel = "ERROR"
    },
}

local rsync_config = {
    archive = true,
    compress = false,
    _extra = {
        "--mkpath",
    },
}

local exclude_list = {
    "README",
}

settings {
    logfile = "/var/log/lsyncd.log",
    statusFile = "/tmp/lsyncd-status.log",
    statusInterval = 20,
    inotifyMode = "CloseWrite or Modify",
    insist = true
}

sync {
    default.rsyncssh,

    source = "/var/log/",
    host = controller,
    targetdir = "/var/log/guest-agent-logs/" .. guest_id .. "/log/",

    delay = 1,
    delete = false,

    exclude = exclude_list,
    rsync = rsync_config,
    ssh = ssh_config,
}

sync {
    default.rsyncssh,

    source = "/var/lib/docker/containers/",
    host = controller,
    targetdir = "/var/log/guest-agent-logs/" .. guest_id .. "/containers/",

    delay = 1,
    delete = false,

    exclude = exclude_list,
    rsync = rsync_config,
    ssh = ssh_config,
}
