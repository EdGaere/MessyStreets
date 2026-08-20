"""
insert_noise.py: Insert noise into a string

NOTES

CHANGE LOG
edward | 2023-06-12 | init

BACKLOG
- insert string.punctuation

USAGE - DATETIME
python3 insert_noise.py "23 février 1923 13:56:21 CET" --noise_level 2 --noise_prob 1.0


"""
from random import uniform, randint, choice
from string import ascii_lowercase, whitespace, digits
from typing import Union, Tuple

from serentec.utils.check_isinstance import check_isinstance

class InsertNoise:

    def __init__(self, noise_level : int, p_noise : float = None):

        """
        :param noise_level: level of noise to be inserted, currently supports 0, 1 or 2
            - None or 0: no noise
            - 1: ascii_lowercase only, single character
            - 2: ascii_lowercase + whitespace, one or two characters

        :param p_noise: probability of inserting noise
            if None, no Noise is inserted (equivalent to noise_level 0)
        """

        self.noise_level = noise_level

        if self.noise_level is None:
            self.p_noise = 0.0

        elif self.noise_level == 0:
            self.p_noise = 0.0

        elif self.noise_level == 1:
            # noise level 1: low noise level
            # ascii_lowercase only
            self.p_noise = 0.05 if p_noise is None else p_noise
            self.max_random_characters = 1
            self.random_character_space = ascii_lowercase

        elif self.noise_level == 2:
            # ascii_lowercase + whitespace
            self.p_noise = 0.05 if p_noise is None else p_noise
            self.max_random_characters = 2
            # NOTE: ascii_lowercase and whitespace are just strings => can be concatenated
            self.random_character_space = ascii_lowercase + whitespace
        
        elif self.noise_level == 3:
            # ascii_lowercase + whitespace + digits
            self.p_noise = 0.05 if p_noise is None else p_noise
            self.max_random_characters = 2
            # NOTE: ascii_lowercase, whitespace and digits are just strings => can be concatenated
            self.random_character_space = ascii_lowercase + whitespace + digits

        else:
            raise ValueError(f"unhandled value {noise_level} for noise_level")

    def is_active(self):
        return self.noise_level is not None and self.noise_level >= 1

    def insert_noise (self, _input : str, return_details : bool = False) -> Union[str, Tuple[str, Tuple[int, str]]]:
        """
        insert noise into the string

        :param input_str: a string with noise to be inserted

        :param return_details: return details on the inserted noise
            if False

        :return: string with noise inserted
            - if return_details is False, a single string is returned
            
            - if return_details is True, a 2-tuple is returned
                1. string with noise inserted

                2. a 2-tuple:
                  1. noise_start_location: location of the start of the noise insertion;
                    None if no noise was inserted
                  
                  2. noise_string: the noise that was inserted
                    None if no noise was inserted
                    

        """

        check_isinstance(_input, str)

        noise_location = None
        noise_string = None
        

        # insert noise
        if self.noise_level is not None and self.noise_level >= 1 and uniform(0.0, 1.0) < self.p_noise:

            # random start location; note: ub is inclusive => at end of string
            noise_location = randint(0, len(_input))

            # random length
            noise_length = randint(1, self.max_random_characters)

            # generate random string
            noise_string = ''.join(choice(self.random_character_space) for i in range(noise_length))

            # insert random string
            _input = _input[0:noise_location] + noise_string + _input[noise_location:]

        if return_details is False:
            return _input
        else:
            return _input, (noise_location, noise_string)

                   

if __name__ == '__main__':

    from argparse import ArgumentParser
    
   
    def main():
        parser = ArgumentParser(description='Insert noise into a string')
        parser.add_argument('input_string', default=None, type=str, help='location to save the data in datasets/')

        # noise options
        parser.add_argument('-n', '--noise_level', type=int, help='noise level, e.g 1, 2, 3', default=0)
        parser.add_argument('-p', '--noise_prob', type=float, help='noise probability', default=None)

        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        
        args = parser.parse_args()

        insert_noise = InsertNoise(args.noise_level, p_noise=args.noise_prob)
        output_string, (noise_location, noise_string) = insert_noise.insert_noise(args.input_string, return_details=True)

        print(f"INP : {args.input_string}")
        print(f"OUT : {output_string}")

        # show location of the inserted noise
        cursor = [" " for _ in range(6) ]
        cursor += [" " for _ in range(noise_location) ]
        cursor += ["^" for _ in range(len(noise_string)) ]
        print("".join(cursor))

    main()