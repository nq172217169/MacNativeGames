/* The Witcher 3.app launcher: points the runtime at the game files bundled in this app and the player's data folder,
   then runs it. The runtime resolves rewritten/local and extracted/local/romfs relative to its cwd (loader.c, romfs.c),
   so this launcher chdirs to Contents/Resources/game, which mirrors the work folder's layout.

   App:    Contents/MacOS/W3 (this); Contents/Resources/game/{build/w3-native,
           build/shader-service/totk_xlate, build/spirv-cross/spirv-cross, rewritten/local,
           extracted/local/romfs/{index.json, runtime-index.bin, romfs.bin}} (scripts/package_app.py).
   Data:   ~/Library/Application Support/MacNativeGames/W3 (W3_DATA_DIR overrides): profile/ (saves), shader-cache/,
           game-slot/, commands.txt, last-run.log. The GPU switches follow games/w3/README.md. */
#include <errno.h>
#include <fcntl.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define NAME "The Witcher 3"

static void join(char *out, const char *dir, const char *name) {
    if (snprintf(out, PATH_MAX, "%s/%s", dir, name) >= PATH_MAX) { fputs("path too long\n", stderr); exit(1); }
}

/* Locate Contents/Resources/game from this executable's real path (works for a staged .app.partial too). */
static int find_game(char *game, size_t n) {
    char exe[PATH_MAX], real[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) || !realpath(exe, real)) return -1;
    char *macos = dirname(real);                       /* .../Contents/MacOS */
    char *contents = dirname(macos);                   /* .../Contents */
    char tmp[PATH_MAX];
    join(tmp, contents, "Resources");
    char game_path[PATH_MAX]; join(game_path, tmp, "game");
    if (realpath(game_path, game) == NULL) return -1;
    (void)n;
    return 0;
}

int main(int argc, char **argv) {
    int check = argc == 2 && !strcmp(argv[1], "--check");
    if (argc != 1 && !check) { fprintf(stderr, "usage: %s [--check]\n", NAME); return 2; }

    char game[PATH_MAX];
    if (find_game(game, sizeof game)) { fprintf(stderr, NAME ": bundled game data not found in this app\n"); return 1; }
    char runtime[PATH_MAX], translator[PATH_MAX], modules[PATH_MAX], main_module[PATH_MAX], romfs[PATH_MAX];
    join(runtime, game, "build/w3-native");
    join(translator, game, "build/shader-service/totk_xlate");
    join(modules, game, "rewritten/local");
    join(main_module, modules, "main.patched.bin");
    join(romfs, game, "extracted/local/romfs");
    if (access(runtime, X_OK)) { perror(NAME ": missing runtime"); return 1; }
    if (access(translator, X_OK)) { perror(NAME ": missing shader translator"); return 1; }
    if (access(main_module, R_OK)) { perror(NAME ": missing game data"); return 1; }
    if (check) { puts(NAME " launcher: runtime, translator and game data present; game was not launched"); return 0; }

    const char *override = getenv("W3_DATA_DIR");
    char data[PATH_MAX];
    if (override && *override) snprintf(data, sizeof data, "%s", override);
    else {
        const char *home = getenv("HOME");
        if (!home) { fputs("no HOME\n", stderr); return 1; }
        snprintf(data, sizeof data, "%s/Library/Application Support/MacNativeGames/W3", home);
    }
    char profile[PATH_MAX], cache[PATH_MAX], slot[PATH_MAX], commands[PATH_MAX], log[PATH_MAX];
    join(profile, data, "profile"); join(cache, data, "shader-cache");
    join(slot, data, "game-slot"); join(commands, data, "commands.txt"); join(log, data, "last-run.log");
    mkdir(data, 0755); mkdir(profile, 0700); mkdir(cache, 0755); mkdir(slot, 0755);
    FILE *cf = fopen(commands, "w"); if (cf) fclose(cf);

    /* GPU safeguards from games/w3/README.md (the same ones the verified headless/title runs used). */
    setenv("TOTK_GPU_ALLOW_SUBMIT", "1", 1);
    setenv("TOTK_GPU_WIDEN", "1", 1);
    setenv("TOTK_GPU_BLOCKRT", "1", 1);
    setenv("TOTK_GPU_MIDCLEAR", "1", 1);
    setenv("TOTK_GPU_KEEPALIVE", "0", 1);
    setenv("TOTK_GPU_BUDGET_MB", "4500", 1);
    setenv("TOTK_GPU_HANG_S", "8", 1);
    setenv("TOTK_PROFILE_DIR", profile, 1);
    setenv("TOTK_SHADER_CACHE", cache, 1);
    setenv("TOTK_ROMFS", romfs, 1);
    setenv("TOTK_ROMFS_PROOF_DIR", data, 1);
    setenv("TOTK_GAME_SLOT_DIR", slot, 1);
    setenv("TOTK_INPUT_FILE", commands, 1);
    setenv("TOTK_SLOT_OWNER", "user", 1);
    setenv("TOTK_SLOT_PURPOSE", "The Witcher 3.app", 1);
    for (const char *const *v = (const char *const[]){"TOTK_HEADLESS", "TOTK_INPUT_SCRIPT", "TOTK_AUTOLOAD", NULL}; *v; v++)
        unsetenv(*v);

    /* The runtime resolves modules and RomFS relative to cwd: run from the bundled game folder. */
    if (chdir(game)) { perror(NAME ": chdir bundled game folder"); return 1; }
    char previous[PATH_MAX]; join(previous, data, "previous-run.log");
    rename(log, previous);
    int fd = open(log, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); close(fd); }
    execl(runtime, "w3-native", "rewritten/local", "boot", (char *)NULL);
    perror(NAME ": could not start the game");
    return 127;
}
