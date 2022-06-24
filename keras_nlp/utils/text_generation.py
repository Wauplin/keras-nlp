# Copyright 2022 The KerasNLP Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Text generation utilities."""

import tensorflow as tf


def validate_prompt(prompt):
    """Helper function to validate input to text_generation utils."""
    if isinstance(prompt, tf.RaggedTensor):
        raise ValueError(
            "RaggedTensor `prompt` is not supported, please "
            "provide `prompt` as a list or Tensor."
        )
    if not isinstance(prompt, tf.Tensor):
        prompt = tf.convert_to_tensor(prompt)
    return prompt


def validate_token_probability_fn(token_probability_fn, prompt):
    """Helper function to validate token probability fn output"""
    test_pred = token_probability_fn(prompt)
    if len(test_pred.shape) != 2:
        raise ValueError(
            "Output of `token_probability_fn` is not a 2D tensor, "
            "please provide a function with the output shape "
            "[batch_size, vocab_size]."
        )


def mask_tokens_after_end_token(prompt, max_length, end_token_id, pad_token_id):
    """Helper function to mask the tokens after the end token."""
    # Mask out tokens after `end_token_id` is encountered.
    # Find index of first end_token_id.
    end_indices = tf.math.argmax(prompt == end_token_id, -1)
    # Use max_length if no `end_token_id` is found.
    end_indices = tf.where(end_indices == 0, max_length, end_indices)
    # Build a mask including end_token and replace tokens after end_token
    # with `pad_token_id`.
    valid_indices = tf.sequence_mask(end_indices + 1, maxlen=max_length)
    return tf.where(valid_indices, prompt, pad_token_id)


def greedy_search(
    token_probability_fn,
    prompt,
    max_length,
    end_token_id=None,
    pad_token_id=0,
):
    """
    Text generation utility based on greedy search.

    Greedy search always appends the token having the largest probability to
    existing sequence.

    Args:
        token_probability_fn: a callable, which takes in input_sequence
            and output the probability distribution or the logits of the next
            token.
        prompt: a list or a Tensor, can be 1D or 2D, the initial tokens to
            append generated tokens.
        max_length: int. The max length of generated text.
        end_token_id: int, defaults to None. The token marking the end of the
            sequence, once encountered the generation is finished for the exact
            sequence. If None, every sequence is generated up to `max_length`.
            If set, all tokens after encountering `end_token_id` will be
            replaced with `pad_token_id`.
        pad_token_id: int, defaults to 0. The pad token after `end_token_id`
            is received.

    Returns:
        A 1D int Tensor, or 2D int RaggedTensor representing the generated
        sequences.

    Examples:
    ```python
    BATCH_SIZE = 8
    VOCAB_SIZE = 10
    FEATURE_SIZE = 16
    START_ID = 1
    END_ID = 2

    # Create a dummy model to predict the next token.
    model = tf.keras.Sequential(
        [
            tf.keras.Input(shape=[None]),
            tf.keras.layers.Embedding(
                input_dim=VOCAB_SIZE,
                output_dim=FEATURE_SIZE,
            ),
            tf.keras.layers.Dense(VOCAB_SIZE, activation="softmax"),
        ]
    )

    # Define a function that outputs the next token's probability given the
    # input sequence.
    def token_probability_fn(inputs):
        return model(inputs)[:, -1, :]

    prompt = tf.fill((BATCH_SIZE, 1), START_ID)

    # Print the generated sequence (token ids).
    keras_nlp.utils.greedy_search(
        token_probability_fn,
        prompt,
        max_length=10,
        end_token_id=END_ID,
    )
    ```

    """
    if not tf.executing_eagerly():
        raise RuntimeError(
            "`keras_nlp.utils.greedy_search` currently requires an eager "
            "execution context. Please call `greedy_search` outside "
            "tf.function or run `tf.config.run_functions_eagerly(True)` to run "
            "tf.function in eager mode."
        )

    prompt = validate_prompt(prompt)

    input_is_1d = prompt.shape.rank == 1
    if input_is_1d:
        prompt = prompt[tf.newaxis, :]
    validate_token_probability_fn(token_probability_fn, prompt)

    i = prompt.shape[1]
    while i < max_length:
        # If the prompt has reached our desired length, exit while loop.
        pred = token_probability_fn(prompt)
        next_token = tf.cast(tf.argmax(pred, axis=-1), dtype=prompt.dtype)
        # Append the next token to current sequence.
        prompt = tf.concat([prompt, next_token[:, tf.newaxis]], axis=-1)
        i += 1

    if end_token_id is not None:
        prompt = mask_tokens_after_end_token(
            prompt, max_length, end_token_id, pad_token_id
        )

    if input_is_1d:
        return tf.squeeze(prompt)
    return prompt


def random_search(
    token_probability_fn,
    prompt,
    max_length,
    seed=None,
    from_logits=False,
    end_token_id=None,
    pad_token_id=0,
):
    """
    Text generation utility based on randomly sampling the entire probability
    distribution.

    Random sampling samples the next token from the probability distribution
    provided by `token_probability_fn` and appends it to the existing sequence.

    Args:
        token_probability_fn: a callable, which takes in input_sequence
            and output the probability distribution of the next token. If
            `from_logits` set to True, it should output the logits of the next
            token.
        prompt: a list or a Tensor, can be 1D or 2D, the initial tokens to
            append generated tokens.
        max_length: int. The max length of generated text.
        seed: int, defaults to None. The random seed used for sampling.
        from_logits: bool. Indicates whether `token_probability_fn` outputs
            logits or probabilities.
        end_token_id: int, defaults to None. The token marking the end of the
            sequence, once encountered the generation is finished for the exact
            sequence. If None, every sequence is generated up to `max_length`.
            If set, all tokens after encountering `end_token_id` will be
            replaced with `pad_token_id`.
        pad_token_id: int, defaults to 0. The pad token after `end_token_id`
            is received.

    Returns:
        A 1D int Tensor, or 2D int Tensor representing the generated
        sequences.

    Examples:
    ```python
    BATCH_SIZE = 8
    VOCAB_SIZE = 10
    FEATURE_SIZE = 16
    START_ID = 1
    END_ID = 2

    # Create a dummy model to predict the next token.
    model = tf.keras.Sequential(
        [
            tf.keras.Input(shape=[None]),
            tf.keras.layers.Embedding(
                input_dim=VOCAB_SIZE,
                output_dim=FEATURE_SIZE,
            ),
            tf.keras.layers.Dense(VOCAB_SIZE, activation="softmax"),
        ]
    )

    # Define a function that outputs the next token's probability given the
    # input sequence.
    def token_probability_fn(inputs):
        return model(inputs)[:, -1, :]

    prompt = tf.fill((BATCH_SIZE, 1), START_ID)

    # Print the generated sequence (token ids).
    keras_nlp.utils.random_search(
        token_probability_fn,
        prompt,
        max_length=10,
        end_token_id=END_ID,
    )
    ```

    """
    if not tf.executing_eagerly():
        raise RuntimeError(
            "`keras_nlp.utils.random_sampling` currently requires an eager "
            "execution context. Please call `random_sampling` outside "
            "tf.function or run `tf.config.run_functions_eagerly(True)` to run "
            "tf.function in eager mode."
        )

    prompt = validate_prompt(prompt)
    input_is_1d = prompt.shape.rank == 1
    if input_is_1d:
        prompt = prompt[tf.newaxis, :]
    validate_token_probability_fn(token_probability_fn, prompt)

    i = prompt.shape[1]
    while i < max_length:
        # If the prompt has reached our desired length, exit while loop.
        pred = token_probability_fn(prompt)
        if from_logits:
            pred = tf.keras.activations.softmax(pred, axis=-1)
        next_token = tf.cast(
            tf.random.categorical(tf.math.log(pred), 1, seed=seed),
            dtype=prompt.dtype,
        )
        # Append the next token to current sequence.
        prompt = tf.concat([prompt, next_token], axis=-1)
        i += 1

    if end_token_id is not None:
        prompt = mask_tokens_after_end_token(
            prompt, max_length, end_token_id, pad_token_id
        )
    if input_is_1d:
        return tf.squeeze(prompt)
    return prompt


def top_k_search(
    token_probability_fn,
    prompt,
    max_length,
    k,
    seed=None,
    from_logits=False,
    end_token_id=None,
    pad_token_id=0,
):
    """
    Text generation utility based on top-k sampling.

    Top-k search samples the next token from the top-k tokens in the
    probability distribution provided by `token_probability_fn` and appends it
    to the existing sequence.

    Args:
        token_probability_fn: a callable, which takes in input_sequence
            and output the probability distribution of the next token. If
            `from_logits` set to True, it should output the logits of the next
            token.
        prompt: a list or a Tensor, can be 1D or 2D, the initial tokens to
            append generated tokens.
        max_length: int. The max length of generated text.
        k: int. The number of top tokens to sample from. Should be non-negative
            and less than the vocabulary size.
        seed: int, defaults to None. The random seed used for sampling.
        from_logits: bool. Indicates whether `token_probability_fn` outputs
            logits or probabilities.
        end_token_id: int, defaults to None. The token marking the end of the
            sequence, once encountered the generation is finished for the exact
            sequence. If None, every sequence is generated up to `max_length`.
            If set, all tokens after encountering `end_token_id` will be
            replaced with `pad_token_id`.
        pad_token_id: int, defaults to 0. The pad token after `end_token_id`
            is received.

    Returns:
        A 1D int Tensor, or 2D int Tensor representing the generated
        sequences.

    Examples:
    ```python
    BATCH_SIZE = 8
    VOCAB_SIZE = 10
    FEATURE_SIZE = 16
    START_ID = 1
    END_ID = 2

    # Create a dummy model to predict the next token.
    model = tf.keras.Sequential(
        [
            tf.keras.Input(shape=[None]),
            tf.keras.layers.Embedding(
                input_dim=VOCAB_SIZE,
                output_dim=FEATURE_SIZE,
            ),
            tf.keras.layers.Dense(VOCAB_SIZE, activation="softmax"),
        ]
    )

    # Define a function that outputs the next token's probability given the
    # input sequence.
    def token_probability_fn(inputs):
        return model(inputs)[:, -1, :]

    prompt = tf.fill((BATCH_SIZE, 1), START_ID)

    # Print the generated sequence (token ids).
    keras_nlp.utils.top_k_search(
        token_probability_fn,
        prompt,
        max_length=10,
        k=4,
        end_token_id=END_ID,
    )
    ```

    """
    if not tf.executing_eagerly():
        raise RuntimeError(
            "`keras_nlp.utils.top_k_search` currently requires an eager "
            "execution context. Please call `top_k_search` outside "
            "tf.function or run `tf.config.run_functions_eagerly(True)` to run "
            "tf.function in eager mode."
        )
    if k <= 0:
        raise ValueError("k should be strictly positive (greater than 0).")

    prompt = validate_prompt(prompt)
    input_is_1d = prompt.shape.rank == 1
    if input_is_1d:
        prompt = prompt[tf.newaxis, :]
    validate_token_probability_fn(token_probability_fn, prompt)

    i = prompt.shape[1]
    while i < max_length:
        # If the prompt has reached our desired length, exit while loop.
        pred = token_probability_fn(prompt)
        if from_logits:
            pred = tf.keras.activations.softmax(pred, axis=-1)
        # If k is greater than the vocabulary size, use the entire vocabulary.
        k = min(k, pred.shape[1])
        # Filter out top-k tokens.
        top_k_pred, top_k_indices = tf.math.top_k(pred, k=k)
        # Sample the next token from the probability distribution.
        next_token = tf.random.categorical(
            tf.math.log(top_k_pred), 1, seed=seed
        )
        # Rearrange to get the next token idx from the original order.
        next_token = tf.gather_nd(top_k_indices, next_token, batch_dims=1)
        next_token = tf.cast(next_token, dtype=prompt.dtype)
        # Append the next token to current sequence.
        prompt = tf.concat([prompt, next_token[:, tf.newaxis]], axis=-1)
        i += 1

    if end_token_id is not None:
        prompt = mask_tokens_after_end_token(
            prompt, max_length, end_token_id, pad_token_id
        )
    if input_is_1d:
        return tf.squeeze(prompt)
    return prompt