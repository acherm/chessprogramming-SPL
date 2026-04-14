CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -pedantic -pthread
CPPFLAGS ?= -Ic_engine_pl/include -Ic_engine_pl/include/generated
LDFLAGS ?= -pthread

SRC := $(wildcard c_engine_pl/src/*.c)
OBJ := $(patsubst c_engine_pl/src/%.c,c_engine_pl/build/%.o,$(SRC))
BIN := c_engine_pl/build/engine_pl
VARIANT_HEADER := c_engine_pl/include/generated/variant_config.h

.PHONY: all clean

all: $(BIN)

$(BIN): $(OBJ)
	@mkdir -p c_engine_pl/build
	$(CC) $(CFLAGS) $(OBJ) -o $@ $(LDFLAGS)

c_engine_pl/build/%.o: c_engine_pl/src/%.c $(VARIANT_HEADER)
	@mkdir -p c_engine_pl/build
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

clean:
	rm -rf c_engine_pl/build
